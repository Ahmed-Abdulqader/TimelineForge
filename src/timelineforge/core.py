import csv
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

class Event:
    """Represents a single normalized forensic log entry."""

    def __init__(self, timestamp: datetime, source: str, event_type: str, message: str, raw_line: str):
        self.timestamp = timestamp
        self.source = source
        self.event_type = event_type
        self.message = message
        self.raw_line = raw_line

    def to_dict(self) -> dict:
        """Serializes event fields into a dictionary for JSON exporting."""
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            "source": self.source,
            "event_type": self.event_type,
            "message": self.message,
            "raw_line": self.raw_line,
        }

    def to_csv_row(self) -> list:
        """Returns event fields as a list matching CSV column order."""
        return [
            self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            self.source,
            self.event_type,
            self.message,
            self.raw_line,
        ]

    def __repr__(self) -> str:
        return f"<Event {self.timestamp} | {self.source} | {self.event_type}>"


from datetime import datetime
from typing import List, Union

class Timeline:
    """Container and processing engine for forensic Event objects."""

    def __init__(self):
        self.events: List[Event] = []

    def add_event(self, event: Event) -> None:
        """Appends a new Event instance to the timeline."""
        self.events.append(event)

    def sort(self) -> None:
        """Sorts all events chronologically in-place."""
        self.events.sort(key=lambda e: e.timestamp)

    def filter_by_date(self, start_date: datetime, end_date: datetime) -> "Timeline":
        """
        Filters events within a datetime range.
        Returns a new Timeline instance to allow method chaining.
        """
        filtered_timeline = Timeline()
        for event in self.events:
            # Direct comparison supports both datetime and date objects safely
            if start_date <= event.timestamp <= end_date:
                filtered_timeline.add_event(event)
        return filtered_timeline

    def filter_by_keyword(self, keyword: str) -> "Timeline":
        """
        Performs a case-insensitive substring search on message, source, and raw line.
        Returns a new Timeline instance to allow method chaining.
        """
        filtered_timeline = Timeline()
        kw = keyword.lower()
        for event in self.events:
            # Substring search using 'in' operator across attributes
            if (kw in event.message.lower() or 
                kw in event.source.lower() or 
                kw in event.raw_line.lower()):
                filtered_timeline.add_event(event)
        return filtered_timeline

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)

import csv
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

# Assuming Event is imported from core/defined above


class BaseParser(ABC):

    @abstractmethod
    def parse(self, file_path: str) -> List[Event]:
        """Parses a log file and returns a list of Event objects."""
        pass

    def parse_timestamp(self, ts_str: str, date_format: str) -> datetime:
        """Helper to safely parse datetime strings."""
        try:
            return datetime.strptime(ts_str, date_format)
        except ValueError as e:
            raise ValueError(
                f"Could not parse timestamp '{ts_str}' with format '{date_format}': {e}"
            )


class SyslogParser(BaseParser):

    def parse(self, file_path: str) -> List[Event]:
        events = []
        # Pattern: Month Day HH:MM:SS Hostname Process/Message
        pattern = re.compile(
            r"^([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$"
        )
        current_year = datetime.now().year

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                match = pattern.match(line_str)
                if match:
                    raw_ts, hostname, msg = match.groups()

                    # Prepend current year since syslog omits the year field
                    full_ts_str = f"{current_year} {raw_ts}"
                    # Format matching: '2026 Oct 11 14:32:00' or '2026 Oct  4 14:32:00'
                    ts = self.parse_timestamp(full_ts_str, "%Y %b %d %H:%M:%S")

                    events.append(
                        Event(
                            timestamp=ts,
                            source=f"syslog:{hostname}",
                            event_type="syslog",
                            message=msg,
                            raw_line=line_str,
                        )
                    )
        return events


class WebLogParser(BaseParser):

    def parse(self, file_path: str) -> List[Event]:
        events = []
        # Combined Log Format: IP - - [DD/Mon/YYYY:HH:MM:SS +TZ] "GET / HTTP/1.1" Status
        pattern = re.compile(
            r'^(\S+)\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"([^"]+)"\s+(\d{3})'
        )

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                match = pattern.match(line_str)
                if match:
                    client_ip, raw_ts, request, status_code = match.groups()

                    # Strip timezone offset for simplified local datetime parsing
                    ts_no_tz = raw_ts.split()[0]  # e.g., "10/Sep/2026:21:35:40"
                    ts = self.parse_timestamp(ts_no_tz, "%d/%b/%Y:%H:%M:%S")

                    events.append(
                        Event(
                            timestamp=ts,
                            source=f"web:{client_ip}",
                            event_type=f"HTTP-{status_code}",
                            message=request,
                            raw_line=line_str,
                        )
                    )
        return events


class CSVParser(BaseParser):

    def parse(self, file_path: str) -> List[Event]:
        events = []

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Flexible field extraction supporting common CSV column names
                raw_ts = (
                    row.get("timestamp") or row.get("datetime") or row.get("time")
                )
                source = (
                    row.get("source") or row.get("host") or "csv_import"
                )
                event_type = (
                    row.get("event_type") or row.get("type") or "generic_csv"
                )
                message = (
                    row.get("message")
                    or row.get("msg")
                    or row.get("details")
                    or ""
                )

                if raw_ts:
                    # Tries ISO 8601 parsing; falls back to standard datetime formats
                    try:
                        ts = datetime.fromisoformat(raw_ts)
                    except ValueError:
                        ts = self.parse_timestamp(
                            raw_ts, "%Y-%m-%d %H:%M:%S"
                        )

                    events.append(
                        Event(
                            timestamp=ts,
                            source=source,
                            event_type=event_type,
                            message=message,
                            raw_line=str(row),
                        )
                    )
        return events

class Exporter:
    """Handles serializing normalized Timeline objects to CSV or JSON files."""

    def to_csv(self, timeline, output_path: str) -> None:
        """Exports all timeline events into a structured CSV file."""
        headers = ["Timestamp", "Source", "Event Type", "Message", "Raw Line"]
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for event in timeline.events:
                writer.writerow(event.to_csv_row())

    def to_json(self, timeline, output_path: str) -> None:
        """Exports all timeline events into a formatted JSON array file."""
        events_data = [event.to_dict() for event in timeline.events]
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(events_data, f, indent=4, ensure_ascii=False)


class Config:
    """Loads operational settings with safe default fallbacks."""

    DEFAULT_CONFIG = {
        "log_level": "INFO",
        "default_export_format": "csv",
        "date_format": "%Y-%m-%d %H:%M:%S",
        "max_log_lines": 10000
    }

    def load(self, config_path: str = "config.json") -> Dict[str, Any]:
        """
        Reads config.json using standard json.load().
        Returns fallback default values if the file is missing or malformed.
        """
        path = Path(config_path)
        if not path.is_file():
            return self.DEFAULT_CONFIG

        try:
            with open(path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                # Merge user config over defaults
                config = self.DEFAULT_CONFIG.copy()
                config.update(user_config)
                return config
        except (json.JSONDecodeError, OSError):
            return self.DEFAULT_CONFIG      

if __name__ == "__main__":
    print(datetime.now().date())