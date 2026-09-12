# TimelineForge

**TimelineForge** is a lightweight, command-line digital forensics tool built in pure Python. It is designed to aggregate, normalize, and chronologically sort disparate system log files into a unified forensic "super-timeline" for incident response analysis.

## Features
* **Multi-Format Parsing:** Native support for Linux syslogs (`auth.log`, `syslog`), Web server access logs (Apache/Nginx), and structured CSV/JSON exports.
* **Timestamp Normalization:** Automatically extracts and standardizes heterogeneous time formats into a uniform timeline.
* **Advanced Filtering:** Filter forensic events by specific date ranges or text keywords.
* **Flexible Exporting:** Output normalized timelines to structured CSV or JSON formats for reporting or further analysis.
* **Zero Dependencies:** Built entirely using Python's standard library, adhering to strict operational constraints.

## Prerequisites
* Python >= 3.14
* [uv](https://github.com/astral-sh/uv) package manager

## Installation

Since the project uses modern Python packaging with `uv`, installation and execution are handled directly from the project root:

1. Clone the repository and navigate to the project root:
   ```bash
   cd TimelineForge

```

2. Build and run the tool using `uv`:
```bash
uv run timelineforge --help

```



## Usage

TimelineForge is driven by the `parse` subcommand. You must specify the input files, the log type, and the output destination.

### Basic Syntax

```bash
uv run timelineforge parse <INPUT_FILES> --type <LOG_TYPE> --output <OUTPUT_FILE>

```

### Command-Line Arguments

| Argument | Description | Required |
| --- | --- | --- |
| `input_files` | One or more log files to parse (positional) | Yes |
| `--type` | Log format: `syslog`, `web`, or `csv` | Yes |
| `--output` | Destination path for the timeline report | Yes |
| `--format` | Output format: `csv` or `json` (Default: `csv`) | No |
| `--start` | Filter start date (ISO format: `YYYY-MM-DD`) | No |
| `--end` | Filter end date (ISO format: `YYYY-MM-DD`) | No |
| `--grep` | Case-insensitive keyword search | No |
| `--config` | Path to custom `config.json` | No |
| `--log-level` | Logging verbosity: `INFO`, `DEBUG`, `ERROR` | No |

### Examples

**1. Parse a standard Linux syslog and export to CSV:**

```bash
uv run timelineforge parse /var/log/syslog --type syslog --output syslog_timeline.csv

```

**2. Parse web access logs, filtering for a specific date range, and export to JSON:**

```bash
uv run timelineforge parse access.log --type web --start 2026-10-10 --end 2026-10-12 --format json --output incident_web.json

```

**3. Parse an authentication log looking for specific failure keywords:**

```bash
uv run timelineforge parse auth.log --type syslog --grep "failed password" --output brute_force_timeline.csv

```

## Architecture

TimelineForge uses a modern `src/` layout:

```text
.
├── pyproject.toml
├── README.md
└── src/
    └── timelineforge/
        ├── __init__.py
        ├── core.py      # Core OOP models (Event, Timeline, Parsers, Exporters)
        └── main.py      # Application entry point and argparse CLI

```

## Author

**Ahmed-Abdulqader**


