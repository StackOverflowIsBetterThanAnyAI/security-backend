import json
import subprocess

SERVICE_NAME = "security.service"
DEFAULT_LINES = 100
MAX_LINES = 500
JOURNAL_TIMEOUT_SECONDS = 10


def message_text(message):
    if isinstance(message, list):
        return bytes(message).decode("utf-8", errors="replace")
    return message or ""


def parse_entry(line):
    try:
        entry = json.loads(line)
        return {
            "time": int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000,
            "priority": int(entry.get("PRIORITY", 6)),
            "message": message_text(entry.get("MESSAGE")),
        }
    except (KeyError, TypeError, ValueError):
        return None


def read(lines=DEFAULT_LINES):
    """The newest log entries of the service, oldest first, or None on failure.

    Reading the system journal without sudo needs the service user in the
    group systemd-journal or adm, which the default Raspberry Pi OS user is.
    """
    try:
        result = subprocess.run(
            [
                "journalctl",
                "--unit",
                SERVICE_NAME,
                "--lines",
                str(lines),
                "--no-pager",
                "--output",
                "json",
                "--output-fields",
                "MESSAGE,PRIORITY",
            ],
            capture_output=True,
            text=True,
            timeout=JOURNAL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    entries = (parse_entry(line) for line in result.stdout.splitlines())
    return [entry for entry in entries if entry is not None]
