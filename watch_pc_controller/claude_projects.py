"""Projects are folders directly inside a few fixed roots.

The watch names a project; it never sends a path. A name is resolved only
among the roots' direct children, so no request can point Claude at a folder
outside them.
"""

import os
import re
from typing import Callable, Optional

from claude_agent_sdk import list_sessions

DEFAULT_ROOTS = [r"D:\Projects", r"D:\project"]
_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")


class UnknownProject(Exception):
    pass


class ProjectExists(Exception):
    pass


class BadProjectName(Exception):
    pass


def project_roots() -> list[str]:
    configured = os.environ.get("PC_CLAUDE_ROOTS")
    roots = configured.split(";") if configured else DEFAULT_ROOTS
    return [os.path.abspath(r) for r in roots if r and os.path.isdir(r)]


def latest_session_time(path: str, lister=list_sessions) -> Optional[int]:
    sessions = lister(directory=path, limit=1)
    return sessions[0].last_modified if sessions else None


def latest_session_id(path: str, lister=list_sessions) -> Optional[str]:
    sessions = lister(directory=path, limit=1)
    return sessions[0].session_id if sessions else None


def list_projects(roots: Optional[list[str]] = None,
                  last_activity: Callable[[str], Optional[int]] = latest_session_time) -> list[dict]:
    projects = []
    for root in roots if roots is not None else project_roots():
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            path = os.path.abspath(entry.path)
            when = last_activity(path)
            if when is None:
                when = int(entry.stat().st_mtime * 1000)
            projects.append({"name": entry.name, "path": path, "last_activity": int(when)})
    projects.sort(key=lambda p: p["last_activity"], reverse=True)
    return projects


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not name or not _NAME_OK.match(name) or ".." in name:
        raise BadProjectName(name)
    return name


def resolve_project(name: str, roots: Optional[list[str]] = None) -> str:
    try:
        name = _check_name(name)
    except BadProjectName:
        raise
    for root in roots if roots is not None else project_roots():
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and entry.name.lower() == name.lower():
                return os.path.abspath(entry.path)
    raise UnknownProject(name)


def create_project(name: str, roots: Optional[list[str]] = None) -> str:
    name = _check_name(name).replace(" ", "-")
    roots = roots if roots is not None else project_roots()
    if not roots:
        raise BadProjectName("no project roots exist")
    try:
        resolve_project(name, roots)
        raise ProjectExists(name)
    except UnknownProject:
        pass
    path = os.path.join(roots[0], name)
    os.makedirs(path)
    return os.path.abspath(path)


def list_conversations(path: str, lister=list_sessions, limit: int = 20) -> list[dict]:
    # Claude Code's own summary (the title `claude --resume` shows) is often in
    # English; the first thing the user said is in their words, so send both.
    return [
        {
            "session_id": s.session_id,
            "title": s.custom_title or s.summary,
            "first_prompt": (s.first_prompt or "")[:80],
            "last_modified": s.last_modified,
        }
        for s in lister(directory=path, limit=limit)
    ]
