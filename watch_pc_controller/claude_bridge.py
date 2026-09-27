"""Claude's questions and approvals, waiting for an answer from the watch.

Read-only requests inside the project pass on their own. Everything else,
including a read of anything outside the project, becomes an event the watch
shows as a card, and Claude waits until the card is answered, or until half
an hour has gone by, when it is told the user is away and to stop. Every
decision is written to an audit log.
"""

import asyncio
import json
import os
import re
import time
import uuid
from typing import Callable

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from watch_pc_controller.claude_events import tool_label
from watch_pc_controller.claude_risk import HOLD_SECONDS, classify

DEFAULT_TIMEOUT_S = 30 * 60

_PATH_KEYS = ("file_path", "path", "notebook_path")
# Drive paths (C:\x, D:/x) and UNC paths (\\server\share) inside a command.
_ABSOLUTE_PATH = re.compile(r"(?<![\w/\\])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'|;&<>]*")


def _within(root: str, path: str) -> bool:
    """Is `path` (absolute, or relative to the project) inside `root`?"""
    path = str(path)
    if not os.path.isabs(root):
        return not os.path.isabs(path) and ".." not in path
    base = os.path.normcase(os.path.abspath(root))
    full = os.path.normcase(os.path.abspath(os.path.join(root, path)))
    try:
        return os.path.commonpath([base, full]) == base
    except ValueError:                        # another drive
        return False


class AuditLog:
    def __init__(self, path: str):
        self._path = path

    def record(self, entry: dict) -> None:
        line = json.dumps({"ts": time.time(), **entry}, ensure_ascii=False)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def recent(self, limit: int = 100) -> list[dict]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        except FileNotFoundError:
            return []
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


class PermissionBridge:
    def __init__(self, emit: Callable[[dict], None], audit: Callable[[dict], None] = lambda entry: None,
                 timeout_s: float = DEFAULT_TIMEOUT_S, project: str = ""):
        self._emit = emit
        self._audit = audit
        self._timeout = timeout_s
        self._project = project
        self._pending: dict[str, tuple[dict, asyncio.Future]] = {}

    # --------------------------------------------------------- the SDK callback

    async def can_use_tool(self, tool_name: str, tool_input: dict, context):
        if tool_name == "AskUserQuestion":
            return await self._ask(tool_input)
        risk = classify(tool_name, tool_input)
        if risk == "read":
            if self._inside_project(tool_input, context):
                return PermissionResultAllow(updated_input=tool_input)
            risk = "normal"                   # reading outside the project waits for the watch
        return await self._approve(tool_name, tool_input, context, risk)

    def _inside_project(self, tool_input: dict, context) -> bool:
        if getattr(context, "blocked_path", None):
            return False
        for key in _PATH_KEYS:
            value = tool_input.get(key)
            if value and not _within(self._project, value):
                return False
        command = str(tool_input.get("command") or "")
        if ".." in command or "~" in command:
            return False
        return all(_within(self._project, p) for p in _ABSOLUTE_PATH.findall(command))

    async def _approve(self, tool_name, tool_input, context, risk):
        remember = self._remember_suggestions(context)
        request = {
            "type": "approval",
            "id": uuid.uuid4().hex,
            "tool": tool_name,
            "risk": risk,
            "title": getattr(context, "title", None) or tool_label(tool_name, tool_input),
            "description": tool_input.get("description") or getattr(context, "description", None) or "",
            "command": str(tool_input.get("command") or tool_input.get("file_path") or ""),
            "hold_seconds": HOLD_SECONDS[risk],
            "can_remember": bool(remember),
        }
        entry = {"project": self._project, "tool": tool_name, "command": request["command"], "risk": risk}
        answer = await self._wait(request)
        if answer is None:
            self._audit({**entry, "decision": "expired"})
            return PermissionResultDeny(message="The user did not answer in time. Stop here and wait for them.", interrupt=True)
        if answer.get("allow"):
            perms = remember if answer.get("always") else None
            self._audit({**entry, "decision": "allowed", "always": bool(perms)})
            return PermissionResultAllow(updated_input=tool_input, updated_permissions=perms or None)
        reason = str(answer.get("reason") or "").strip()
        self._audit({**entry, "decision": "denied", "reason": reason})
        return PermissionResultDeny(message="The user declined this." + (f" They said: {reason}" if reason else ""))

    async def _ask(self, tool_input):
        questions = tool_input.get("questions", []) or []
        request = {
            "type": "question",
            "id": uuid.uuid4().hex,
            "questions": [
                {
                    "question": q.get("question", ""),
                    "header": q.get("header", ""),
                    "multi": bool(q.get("multiSelect")),
                    "options": [{"label": o.get("label", ""), "description": o.get("description", "")} for o in q.get("options", [])],
                }
                for q in questions
            ],
        }
        answer = await self._wait(request)
        if answer is None:
            return PermissionResultDeny(message="The user did not answer in time.", interrupt=True)
        updated = {"questions": questions, "answers": answer.get("answers", {}) or {}}
        if answer.get("response"):
            updated["response"] = answer["response"]
        return PermissionResultAllow(updated_input=updated)

    @staticmethod
    def _remember_suggestions(context) -> list:
        """'Always in this project' means the rules Claude Code offers for local settings."""
        return [s for s in (getattr(context, "suggestions", None) or []) if getattr(s, "destination", None) == "localSettings"]

    # --------------------------------------------------------- waiting

    async def _wait(self, request: dict):
        future = asyncio.get_running_loop().create_future()
        self._pending[request["id"]] = (request, future)
        self._emit(request)
        try:
            return await asyncio.wait_for(asyncio.shield(future), self._timeout)
        except asyncio.TimeoutError:
            self._emit({"type": "expired", "id": request["id"]})
            return None
        finally:
            self._pending.pop(request["id"], None)

    def answer(self, request_id: str, payload: dict) -> bool:
        entry = self._pending.get(request_id)
        if entry is None or entry[1].done():
            return False
        entry[1].set_result(payload or {})
        self._emit({"type": "answered", "id": request_id})
        return True

    def pending(self) -> list[dict]:
        return [request for request, _ in self._pending.values()]

    def cancel_all(self) -> None:
        for _, future in list(self._pending.values()):
            if not future.done():
                future.set_result({"allow": False, "reason": "interrupted"})
