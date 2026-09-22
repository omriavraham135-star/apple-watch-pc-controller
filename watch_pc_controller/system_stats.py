"""Live machine vitals for the watch's stats page.

CPU temperature is deliberately absent: Windows does not expose it without
administrator rights and extra software, so disk usage takes the third slot.
"""

import os
import time
from typing import Any, Dict

import psutil

_BYTES_PER_GB = 1024 ** 3

# psutil's first non-blocking cpu_percent() call always reports 0.0 because it
# has no previous sample to compare against. Prime it at import so the first
# real request returns a meaningful number.
psutil.cpu_percent(interval=None)


def _system_drive() -> str:
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def _gb(value: int) -> float:
    return round(value / _BYTES_PER_GB, 1)


def get_stats() -> Dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(_system_drive())

    return {
        "cpu": int(round(psutil.cpu_percent(interval=None))),
        "memory": int(round(memory.percent)),
        "disk": int(round(disk.percent)),
        "memory_used_gb": _gb(memory.used),
        "memory_total_gb": _gb(memory.total),
        "disk_free_gb": _gb(disk.free),
        "disk_total_gb": _gb(disk.total),
        "uptime_seconds": int(max(0, time.time() - psutil.boot_time())),
    }
