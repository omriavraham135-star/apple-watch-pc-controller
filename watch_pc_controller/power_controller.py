"""Power actions for the PC: lock, sleep, restart, shutdown.

Commands are a fixed table keyed by action name. Nothing from the network ever
reaches the shell — the caller names an action, and an unrecognised name is
refused before anything runs.
"""

import subprocess
from typing import Any, Callable, Dict, List, Optional, Sequence

LOCK = "lock"
SLEEP = "sleep"
RESTART = "restart"
SHUTDOWN = "shutdown"


class PowerError(Exception):
    """Base class for power failures."""


class UnknownPowerActionError(PowerError):
    """Raised when an action name is not in the supported table."""


def _run(command: Sequence[str]) -> None:
    subprocess.Popen(list(command), shell=False)


class PowerController:
    #: How long the UI must be held before an action fires. Graduated by how
    #: much damage a stray touch would do: a lock is a tap, a shutdown is three
    #: seconds of deliberate intent.
    #:
    #: action -> (argv, human label, destructive, hold seconds)
    _TABLE: Dict[str, Dict[str, Any]] = {
        LOCK: {
            "command": ["rundll32.exe", "user32.dll,LockWorkStation"],
            "label": "נעילה",
            "destructive": False,
            "hold_seconds": 0.0,
        },
        SLEEP: {
            "command": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "label": "שינה",
            "destructive": False,
            "hold_seconds": 0.0,
        },
        RESTART: {
            "command": ["shutdown", "/r", "/t", "0"],
            "label": "הפעלה מחדש",
            "destructive": True,
            "hold_seconds": 2.0,
        },
        SHUTDOWN: {
            "command": ["shutdown", "/s", "/t", "0"],
            "label": "כיבוי",
            "destructive": True,
            "hold_seconds": 3.0,
        },
    }

    def __init__(self, runner: Optional[Callable[[Sequence[str]], None]] = None):
        self._runner = runner or _run

    def available_actions(self) -> List[str]:
        return list(self._TABLE.keys())

    def is_destructive(self, action: str) -> bool:
        entry = self._TABLE.get(action)
        if entry is None:
            raise UnknownPowerActionError(f"unknown power action: {action!r}")
        return bool(entry["destructive"])

    def hold_seconds(self, action: str) -> float:
        entry = self._TABLE.get(action)
        if entry is None:
            raise UnknownPowerActionError(f"unknown power action: {action!r}")
        return float(entry["hold_seconds"])

    def describe(self) -> List[Dict[str, Any]]:
        """What the UI needs to render the page, including how long to hold each."""
        return [
            {
                "action": name,
                "label": entry["label"],
                "destructive": entry["destructive"],
                "hold_seconds": entry["hold_seconds"],
            }
            for name, entry in self._TABLE.items()
        ]

    def execute(self, action: str) -> Dict[str, Any]:
        entry = self._TABLE.get(action)
        if entry is None:
            raise UnknownPowerActionError(f"unknown power action: {action!r}")

        self._runner(entry["command"])
        return {
            "action": action,
            "label": entry["label"],
            "destructive": entry["destructive"],
            "hold_seconds": entry["hold_seconds"],
            "status": "dispatched",
        }
