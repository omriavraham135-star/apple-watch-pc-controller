"""Tells whether an app is already running, and brings it to the front.

This is what lets an action tile know its app is open, and lets tapping it
switch to that window instead of launching a second copy.
"""

import ctypes
import logging
import os
from typing import Dict, Iterable, List, Optional

import psutil

log = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"

# EnumWindows constants
_GW_OWNER = 4
_SW_RESTORE = 9


def running_pids(names: Iterable[str]) -> Dict[str, int]:
    """Map each requested process name to one live pid.

    Matching is case-insensitive because a config file says "chrome.exe" while
    Windows may report "Chrome.exe". Scanning every process costs a few
    milliseconds, which is cheap enough to poll.
    """
    wanted = {n.lower() for n in names if n}
    if not wanted:
        return {}

    found: Dict[str, int] = {}
    for proc in psutil.process_iter(["name", "pid"]):
        name = (proc.info.get("name") or "").lower()
        if name in wanted and name not in found:
            found[name] = proc.info["pid"]
            if len(found) == len(wanted):
                break
    return found


def _user32():
    if not _IS_WINDOWS:
        raise OSError("window focus is only implemented on Windows")
    return ctypes.WinDLL("user32", use_last_error=True)


def _top_level_windows(pid: int) -> List[int]:
    """Visible, titled, un-owned windows belonging to a process."""
    from ctypes import wintypes

    user32 = _user32()
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    hwnds: List[int] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != pid:
            return True
        # Skip tool windows and dialogs owned by another window.
        if user32.GetWindow(hwnd, _GW_OWNER):
            return True
        if user32.GetWindowTextLengthW(hwnd) > 0:
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return hwnds


def focus_pid(pid: Optional[int]) -> bool:
    """Restore and raise a process's main window. False if there was nothing to raise."""
    if not pid or not _IS_WINDOWS:
        return False

    try:
        user32 = _user32()
        for hwnd in _top_level_windows(pid):
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, _SW_RESTORE)
            if user32.SetForegroundWindow(hwnd):
                return True
    except Exception as exc:  # a focus failure must never break the request
        log.warning("could not focus pid %s: %s", pid, exc)
    return False
