"""User-defined shortcut actions, loaded from a local JSON file.

The security property this module exists to hold: the network supplies an
**id**, never a command. Commands live only in the operator's own config file
on the PC, and `list_actions` deliberately withholds them, so a client can ask
for one of a fixed set of things and nothing else.
"""

import json
import logging
import os
import subprocess
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

from watch_pc_controller.process_watch import focus_pid, running_pids

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "actions.json")
DEFAULT_ICON = "bolt"


class ActionsError(Exception):
    """Base class for action failures."""


class UnknownActionError(ActionsError):
    """Raised when an id is not present in the loaded config."""


def _spawn(command: str) -> None:
    """Launch a command and let it outlive this request."""
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen(command, shell=True, creationflags=creation_flags)


class ActionRegistry:
    def __init__(
        self,
        config_path: Optional[Union[str, os.PathLike]] = None,
        runner: Optional[Callable[[str], None]] = None,
        prober: Optional[Callable[[Iterable[str]], Dict[str, int]]] = None,
        focuser: Optional[Callable[[int], bool]] = None,
    ):
        self._config_path = str(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
        self._runner = runner or _spawn
        self._prober = prober or running_pids
        self._focuser = focuser or focus_pid
        self._actions: Dict[str, Dict[str, Any]] = {}
        self.reload()

    @property
    def config_path(self) -> str:
        return self._config_path

    def reload(self) -> None:
        """Re-read the config. A broken or absent file leaves the registry empty."""
        self._actions = {}

        raw = self._read_config()
        if raw is None:
            return

        if not isinstance(raw, list):
            log.warning("actions config must be a list, got %s", type(raw).__name__)
            return

        for entry in raw:
            parsed = self._parse_entry(entry)
            if parsed is None:
                continue
            if parsed["id"] in self._actions:
                log.warning("duplicate action id %r ignored", parsed["id"])
                continue
            self._actions[parsed["id"]] = parsed

    def _read_config(self) -> Optional[Any]:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            log.info("no actions config at %s", self._config_path)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("could not read actions config: %s", exc)
        return None

    @staticmethod
    def _parse_entry(entry: Any) -> Optional[Dict[str, str]]:
        if not isinstance(entry, dict):
            log.warning("skipping non-object action entry")
            return None

        action_id = entry.get("id")
        label = entry.get("label")
        command = entry.get("command")

        if not all(isinstance(v, str) and v.strip() for v in (action_id, label, command)):
            log.warning("skipping action entry missing id, label or command: %r", entry)
            return None

        icon = entry.get("icon")
        if not isinstance(icon, str) or not icon.strip():
            icon = DEFAULT_ICON

        # Optional: the executable to watch, so the tile can show whether the
        # app is already up and a tap can raise it instead of starting another.
        process = entry.get("process")
        if not isinstance(process, str) or not process.strip():
            process = None
        else:
            process = process.strip()

        return {
            "id": action_id,
            "label": label,
            "icon": icon,
            "command": command,
            "process": process,
        }

    def list_actions(self) -> List[Dict[str, Any]]:
        """Everything the watch needs to draw the buttons — and nothing more."""
        return [
            {
                "id": a["id"],
                "label": a["label"],
                "icon": a["icon"],
                "process": a["process"],
            }
            for a in self._actions.values()
        ]

    def statuses(self) -> Dict[str, Dict[str, Any]]:
        """Which actions have their app open right now.

        One sweep of the process table covers every tile: this is polled, so
        scanning per action would multiply the cost for no gain.
        """
        watched = {a["process"] for a in self._actions.values() if a["process"]}
        live = self._prober(watched) if watched else {}

        result: Dict[str, Dict[str, Any]] = {}
        for action in self._actions.values():
            pid = live.get(action["process"].lower()) if action["process"] else None
            result[action["id"]] = {"running": pid is not None, "pid": pid}
        return result

    def run(self, action_id: str) -> Dict[str, Any]:
        action = self._actions.get(action_id)
        if action is None:
            raise UnknownActionError(f"unknown action: {action_id!r}")

        # If the app is already up, raise its window rather than start a second
        # copy. Focus can fail for reasons outside our control (foreground
        # locks, a window that has not drawn yet), so launching stays the
        # fallback — a tap must always do something.
        if action["process"]:
            live = self._prober([action["process"]])
            pid = live.get(action["process"].lower())
            if pid and self._focuser(pid):
                return {
                    "id": action["id"],
                    "label": action["label"],
                    "status": "focused",
                    "pid": pid,
                }

        self._runner(action["command"])
        return {"id": action["id"], "label": action["label"], "status": "launched"}
