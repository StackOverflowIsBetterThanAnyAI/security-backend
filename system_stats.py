import os
import subprocess
import time
from datetime import datetime

from folder_data import (
    HTML_FOLDER_LOCATION,
    IMAGE_FILENAME_PATTERN,
    IMAGE_FOLDER_LOCATION,
    IMAGE_FOLDER_LOCATION_LIVE,
)

THROTTLE_FLAGS = {
    "under_voltage_now": 0,
    "throttled_now": 2,
    "under_voltage_occurred": 16,
    "throttled_occurred": 18,
}


def read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def cpu_temperature():
    raw = read_file("/sys/class/thermal/thermal_zone0/temp")
    return round(int(raw) / 1000, 1) if raw else None


def throttling():
    try:
        output = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
        value = int(output.strip().split("=")[1], 16)
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
    return {name: bool(value & (1 << bit)) for name, bit in THROTTLE_FLAGS.items()}


def memory():
    raw = read_file("/proc/meminfo")
    if not raw:
        return None
    values = {}
    for line in raw.splitlines():
        key, _, rest = line.partition(":")
        values[key] = int(rest.split()[0]) * 1024
    return {
        "total": values.get("MemTotal"),
        "available": values.get("MemAvailable"),
        "swap_total": values.get("SwapTotal"),
        "swap_free": values.get("SwapFree"),
    }


def disk():
    try:
        stat = os.statvfs(HTML_FOLDER_LOCATION)
    except (AttributeError, OSError):
        return None
    return {
        "total": stat.f_blocks * stat.f_frsize,
        "free": stat.f_bavail * stat.f_frsize,
    }


def load_average():
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        return None


def uptime_seconds():
    raw = read_file("/proc/uptime")
    return int(float(raw.split()[0])) if raw else None


def image_age_seconds(filename):
    taken = datetime.strptime(filename, "security_image_%Y-%m-%d_%H-%M-%S.jpg")
    return max(0, int(time.time() - taken.timestamp()))


def images(folder):
    try:
        files = sorted(f for f in os.listdir(folder) if IMAGE_FILENAME_PATTERN.match(f))
    except OSError:
        files = []
    return {
        "count": len(files),
        "newest_age_seconds": image_age_seconds(files[-1]) if files else None,
    }


def collect():
    return {
        "cpu_temperature": cpu_temperature(),
        "disk": disk(),
        "load_average": load_average(),
        "memory": memory(),
        "throttling": throttling(),
        "uptime_seconds": uptime_seconds(),
        "archive": images(IMAGE_FOLDER_LOCATION),
        "live": images(IMAGE_FOLDER_LOCATION_LIVE),
    }
