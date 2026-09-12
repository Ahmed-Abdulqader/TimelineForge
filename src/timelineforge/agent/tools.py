import logging
import platform
import shutil
import subprocess
import time
import json
import csv
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, UsageLimits


DATA_DIR = (Path(__file__).parent.parent.parent / "data").resolve()
GREP_TIMEOUT_SECONDS = 30
READ_MAX_LINES = 200
AGENT_REQUEST_LIMIT = 20

logger = logging.getLogger(__name__)

def _ripgrep_install_hint() -> str:
    """Return the most relevant ripgrep install command for this OS."""
    system = platform.system()

    if system == "Darwin":
        return "Install with `brew install ripgrep`."

    if system == "Windows":
        return "Install with `winget install BurntSushi.ripgrep.MSVC`, `choco install ripgrep`, or `scoop install ripgrep`."

    if system == "Linux":
        # Check for common Linux package managers
        if shutil.which("apt-get"):
            return "Install with `sudo apt-get install ripgrep`."
        if shutil.which("dnf"):
            return "Install with `sudo dnf install ripgrep`."
        if shutil.which("pacman"):
            return "Install with `sudo pacman -S ripgrep`."
        if shutil.which("zypper"):
            return "Install with `sudo zypper install ripgrep`."

        return "Install with your Linux package manager (e.g., `apt`, `dnf`, `pacman`) or cargo (`cargo install ripgrep`)."

# --------------------------------------------------------------
# Step 2: Path validation helper
# --------------------------------------------------------------


def _safe_path(path: str) -> Path | None:
    """Resolve a user-supplied path against DATA_DIR and guard against path traversal."""
    try:
        # Resolve target path relative to DATA_DIR
        target = (DATA_DIR / path).resolve()

        # Strict containment check: path must be strictly inside DATA_DIR
        if not target.is_relative_to(DATA_DIR):
            logger.warning("Path traversal attempt blocked: %r", path)
            return None

        # Prevent pointing directly to the root target directory itself
        if target == DATA_DIR:
            return None

        return target
    except (ValueError, RuntimeError) as e:
        logger.warning("Invalid path argument %r: %s", path, e)
        return None

# --------------------------------------------------------------
# Step 3: grep with ripgrep
# --------------------------------------------------------------

def grep(pattern: str, max_results: int = 30, context: int = 0) -> str:
    """Search CSV and JSON files with ripgrep and return matching `file:line:text` lines.

    Set `context` to include N surrounding lines around each match (rg -C). Recently
    edited files come first via `--sortr=modified`. `--no-config` ignores any user
    `~/.ripgreprc` so behavior is identical across machines.
    """
    logger.info(
        "grep(pattern=%r, max_results=%d, context=%d)", pattern, max_results, context
    )

    if max_results < 1:
        return "Error: max_results must be 1 or greater."
    if context < 0:
        return "Error: context must be 0 or greater."
    if not shutil.which("rg"):
        return f"Error: ripgrep ('rg') is not installed. {_ripgrep_install_hint()}"

    cmd = [
        "rg",
        "--line-number",
        "--no-heading",
        "--ignore-case",
        "--no-config",
        "--sortr=modified",
        "--max-count",
        str(max_results),
        "--glob",
        "*.csv",  # Search CSV files
        "--glob",
        "*.json",  # Search JSON files
        *(["--context", str(context)] if context > 0 else []),
        "--",
        pattern,
        ".",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=DATA_DIR,  # Ensure this points to your DATA_DIR target
            capture_output=True,
            text=True,
            check=False,
            timeout=GREP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("grep timed out for pattern=%r", pattern)
        return f"Error: grep timed out after {GREP_TIMEOUT_SECONDS}s. Try a more specific pattern."

    if result.returncode == 2:
        return f"Error: invalid pattern {pattern!r}: {result.stderr.strip()}"

    if not result.stdout.strip():
        return f"No matches found for pattern: {pattern}"

    lines = result.stdout.splitlines()
    if len(lines) > max_results:
        lines = lines[:max_results] + [
            f"... truncated to {max_results} matches. Try a more specific pattern."
        ]
    return "\n".join(lines)

# --------------------------------------------------------------
# Step 4: list files safely
# --------------------------------------------------------------


def list_files(pattern: str = "*.csv") -> str:
    """List files in the data directory using a glob pattern."""
    logger.info("list_files(pattern=%r)", pattern)

    if not DATA_DIR.exists():
        return f"Error: notes directory not found at {DATA_DIR}"

    try:
        paths = DATA_DIR.glob(pattern)
    except (NotImplementedError, ValueError) as e:
        return f"Error: invalid glob pattern {pattern!r}: {e}"

    matches = sorted(
        str(path.relative_to(DATA_DIR))
        for path in (p.resolve() for p in paths)
        if path.is_file() and path.is_relative_to(DATA_DIR)
    )
    if not matches:
        return f"No files matched pattern: {pattern}"
    return "\n".join(matches)


# --------------------------------------------------------------
# Step 5: read bounded file ranges
# --------------------------------------------------------------


def read_file(path: str, offset: int = 1, limit: int = READ_MAX_LINES) -> str:
    """Read a bounded line range from a file relative to the notes root."""
    logger.info("read_file(path=%r, offset=%d, limit=%d)", path, offset, limit)

    safe = _safe_path(path)
    if safe is None:
        return f"Error: path {path!r} is outside the notes directory."
    if not safe.exists():
        return f"Error: file not found: {path}"
    if not safe.is_file():
        return f"Error: {path} is not a file."
    if offset < 1:
        return "Error: offset must be 1 or greater."
    if limit < 1:
        return "Error: limit must be 1 or greater."
    if limit > READ_MAX_LINES:
        return f"Error: limit must be {READ_MAX_LINES} lines or fewer."

    try:
        lines = safe.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"Error: {path} is not UTF-8 text."

    end = min(offset + limit - 1, len(lines))
    excerpt = lines[offset - 1 : end]
    if not excerpt:
        return f"No lines found. {path} has {len(lines)} lines."
    return "\n".join(f"{i}: {line}" for i, line in enumerate(excerpt, start=offset))



def write_file(filename: str, content: str | list | dict, format: str) -> str:
    """Safely write structured content to a CSV or JSON file within DATA_DIR.

    Args:
        filename: Relative path or filename (must end in .json or .csv).
        content: Data to write.
                 - For JSON: String (valid JSON), dict, or list.
                 - For CSV: String (valid CSV text) or list of dicts/lists.
        format: Format specifier ("json" or "csv").

    Returns:
        Status message string indicating success or failure.
    """
    logger.info("write_file(filename=%r, format=%r)", filename, format)

    # 1. Format validation
    fmt = format.lower().strip()
    if fmt not in ("json", "csv"):
        return "Error: Format must be explicitly specified as 'json' or 'csv'."

    # 2. Strict file extension check (Prevents writing executable scripts or dotfiles)
    target_path = _safe_path(filename)
    if target_path is None:
        return "Error: Access denied. Path must stay strictly within the authorized data directory."

    if fmt == "json" and target_path.suffix.lower() != ".json":
        return "Error: File extension must be '.json' when format='json'."
    if fmt == "csv" and target_path.suffix.lower() != ".csv":
        return "Error: File extension must be '.csv' when format='csv'."

    # 3. Content serialization & validation
    formatted_data: str = ""

    try:
        if fmt == "json":
            if isinstance(content, str):
                # Validate that string content is valid JSON before writing
                parsed = json.loads(content)
                formatted_data = json.dumps(parsed, indent=2, ensure_ascii=False)
            elif isinstance(content, (dict, list)):
                formatted_data = json.dumps(content, indent=2, ensure_ascii=False)
            else:
                return (
                    "Error: Content for JSON must be a dict, list, or valid JSON string."
                )

        elif fmt == "csv":
            if isinstance(content, str):
                formatted_data = content
            elif isinstance(content, list):
                if not content:
                    formatted_data = ""
                else:
                    import io

                    output = io.StringIO()
                    # List of dicts (Header-based CSV)
                    if isinstance(content[0], dict):
                        fieldnames = list(content[0].keys())
                        writer = csv.DictWriter(output, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(content)
                    # List of lists (Row-based CSV)
                    elif isinstance(content[0], (list, tuple)):
                        writer = csv.writer(output)
                        writer.writerows(content)
                    else:
                        return "Error: CSV list content must contain dicts or lists representing rows."
                    formatted_data = output.getvalue()
            else:
                return "Error: Content for CSV must be a string or a list of rows."

    except (json.JSONDecodeError, csv.Error, TypeError, ValueError) as e:
        return f"Error: Content validation failed for format {fmt!r}: {e}"

    # 4. Atomic Write with Security Controls
    try:
        # Ensure target subdirectories exist inside DATA_DIR
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to a hidden temporary file first (Atomic operation)
        # Prevents race conditions and leaves no partial/corrupted files on crash
        temp_dir = target_path.parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=temp_dir,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            tmp_file.write(formatted_data)
            tmp_path = Path(tmp_file.name)

        # Restrict permissions to read/write for owner only (0600 / rw-------)
        tmp_path.chmod(0o600)

        # Atomically move temporary file to final target destination
        tmp_path.replace(target_path)

        return (
            f"Successfully wrote {len(formatted_data)} bytes to {target_path.name}"
        )

    except Exception as e:
        logger.error("Failed to write file %s: %s", target_path, e, exc_info=True)
        # Cleanup temp file if it exists
        if "tmp_path" in locals() and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return f"Error: Failed to write file due to system error: {e}"

def read_file_head(file_path: str, num_lines: int = 10) -> str:
    """Reads the first N lines of a file to inspect its contents or structure.
    
    Args:
        file_path: The path to the file to read (relative to the data directory).
        num_lines: Number of lines to read (defaults to 10).
        
    Returns:
        A string containing the first N lines, or a descriptive error message.
    """
    logger.info("read_file_head(file_path=%r, num_lines=%d)", file_path, num_lines)
    
    # 1. Resolve and validate path using _safe_path
    path = _safe_path(file_path)
    if path is None:
        return "Error: Access denied. Path must stay strictly within the authorized data directory."
    
    # 2. Basic path validation
    if not path.exists():
        return f"Error: The path '{file_path}' does not exist."
    if not path.is_file():
        return f"Error: '{file_path}' is not a file (it might be a directory)."
        
    # 3. Safely read lines
    try:
        lines = []
        # 'errors="replace"' ensures the agent doesn't crash if it accidentally reads a binary file
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(num_lines):
                line = f.readline()
                if not line:
                    break
                # Strip trailing newlines so joining them later is clean
                lines.append(line.rstrip("\n"))
                
        if not lines:
            return f"[File '{file_path}' is completely empty]"
            
        header = f"--- First {len(lines)} lines of {path.name} ---\n"
        return header + "\n".join(lines)
        
    except PermissionError:
        return f"Error: Permission denied. Cannot read '{file_path}'."
    except Exception as e:
        logger.error("Failed to read head of %s: %s", file_path, e, exc_info=True)
        return f"Error: An unexpected issue occurred while reading '{file_path}': {e}"
    
# --------------------------------------------------------------
# Step 6: Structured answer models
# --------------------------------------------------------------


# class Citation(BaseModel):
#     """One source backing a claim in the answer."""

#     file: str = Field(
#         description="Relative path to the markdown file, e.g. '03-incident-2024-q3.md'"
#     )
#     quote: str = Field(description="Exact line(s) from the file that support the claim")


# class SearchAnswer(BaseModel):
#     """Structured answer with citations that downstream code can trust."""

#     answer: str = Field(description="The answer in plain English")
#     citations: list[Citation] = Field(
#         description="Files and quotes that support the answer"
#     )


# # --------------------------------------------------------------
# # Step 7: Production agent
# # --------------------------------------------------------------


# agent = Agent(
#     # "openai:gpt-5.5",
#     "openai:gpt-4.1-nano",  # faster
#     tools=[list_files, grep, read_file],
#     output_type=SearchAnswer,
#     instructions=(
#         "Answer from notes with citations. Use grep context or read_file ranges. "
#         "Adapt to Error/No matches."
#     ),
# )


# # --------------------------------------------------------------
# # Step 8: Run it with a turn cap
# # --------------------------------------------------------------


# if __name__ == "__main__":
#     logging.basicConfig(
#         level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
#     )

#     start = time.perf_counter()
#     result = agent.run_sync(
#         "Why does our nightly deploy job run at 03:47 UTC specifically?",
#         usage_limits=UsageLimits(request_limit=AGENT_REQUEST_LIMIT),
#     )
#     elapsed = time.perf_counter() - start

#     print("\nAgent:", result.output.answer)
#     print("\nCitations:")
#     for citation in result.output.citations:
#         print(f"  - {citation.file}")
#         for line in citation.quote.splitlines():
#             print(f"      {line}")

#     usage = result.usage()
#     print(
#         f"\nUsage: {usage.requests} requests, {usage.tool_calls} tool calls, "
#         f"{usage.input_tokens} input + {usage.output_tokens} output tokens, "
#         f"{elapsed:.1f}s"
#     )