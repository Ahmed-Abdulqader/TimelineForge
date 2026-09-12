import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Import all our domain classes from core.py
from timelineforge.core import (
    Timeline, Event, SyslogParser, WebLogParser, CSVParser, Exporter, Config
)

__version__ = "1.0.0"

def setup_logger(log_level_str: str):
    """Configures the standard Python logger."""
    numeric_level = getattr(logging, log_level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def parse_date(date_str: str) -> datetime:
    """Helper to parse CLI date strings into datetime objects."""
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: '{date_str}'. Use ISO format (e.g., YYYY-MM-DD).")

def build_cli() -> argparse.ArgumentParser:
    """Constructs the command-line interface."""
    parser = argparse.ArgumentParser(
        description="TimelineForge: A forensic timeline builder.",
        epilog="Example: python main.py parse /var/log/syslog --type syslog --output result.csv"
    )

    # Top-level flags
    parser.add_argument("--version", action="version", version=f"TimelineForge v{__version__}")
    parser.add_argument("--config", type=str, default="config.json", help="Path to configuration file.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set the logging level.")

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 'parse' subcommand
    parse_cmd = subparsers.add_parser("parse", help="Parse log files and generate a timeline.")
    parse_cmd.add_argument("input_files", nargs="+", help="One or more log files to parse.")
    parse_cmd.add_argument("--type", choices=["syslog", "web", "csv"], required=True, help="Type of logs being parsed.")
    
    # Filter flags
    parse_cmd.add_argument("--start", type=parse_date, help="Start date (ISO format: YYYY-MM-DD)")
    parse_cmd.add_argument("--end", type=parse_date, help="End date (ISO format: YYYY-MM-DD)")
    parse_cmd.add_argument("--grep", type=str, help="Keyword to search for in events.")

    # Export flags
    parse_cmd.add_argument("--output", type=str, required=True, help="Output file path.")
    parse_cmd.add_argument("--format", choices=["csv", "json"], default="csv", help="Output file format.")

    return parser

def handle_parse_command(args, config_data):
    """Executes the parsing, filtering, and exporting workflow."""
    timeline = Timeline()
    
    # 1. Select the correct parser
    if args.type == "syslog":
        parser_instance = SyslogParser()
    elif args.type == "web":
        parser_instance = WebLogParser()
    elif args.type == "csv":
        parser_instance = CSVParser()

    # 2. Parse all input files
    for file_path in args.input_files:
        path = Path(file_path)
        if not path.is_file():
            logging.error(f"Missing file: '{file_path}' does not exist.")
            sys.exit(1)

        logging.info(f"Parsing {file_path} as {args.type}...")
        try:
            events = parser_instance.parse(str(path))
            for event in events:
                timeline.add_event(event)
        except PermissionError:
            logging.error(f"Insufficient permissions to read '{file_path}'.")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Failed to parse '{file_path}': {e}")
            sys.exit(1)

    # 3. Sort chronologically
    timeline.sort()
    logging.info(f"Loaded {len(timeline)} total events.")

    # 4. Apply Filters
    if args.start and args.end:
        logging.info(f"Filtering dates between {args.start} and {args.end}...")
        timeline = timeline.filter_by_date(args.start, args.end)
    
    if args.grep:
        logging.info(f"Filtering by keyword: '{args.grep}'...")
        timeline = timeline.filter_by_keyword(args.grep)

    if len(timeline) == 0:
        logging.warning("No events match the specified criteria. Exporting empty timeline.")

    # 5. Export Data
    exporter = Exporter()
    output_format = args.format or config_data.get("default_export_format", "csv")
    
    try:
        if output_format == "csv":
            exporter.to_csv(timeline, args.output)
        else:
            exporter.to_json(timeline, args.output)
        logging.info(f"Successfully exported {len(timeline)} events to {args.output}")
    except PermissionError:
        logging.error(f"Insufficient permissions to write to '{args.output}'.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to export data: {e}")
        sys.exit(1)

def main():
    parser = build_cli()
    
    # If no arguments are provided, print help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # Setup configurations and logging
    config_manager = Config()
    config_data = config_manager.load(args.config)
    
    # CLI flag overrides config file
    log_level = args.log_level if args.log_level else config_data.get("log_level", "INFO")
    setup_logger(log_level)

    # Route subcommands
    if args.command == "parse":
        handle_parse_command(args, config_data)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
