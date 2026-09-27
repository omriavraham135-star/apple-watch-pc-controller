"""Spoken conversations with Claude Code, one per open project session.

A conversation owns one SDK client running in the project folder with the
user's own settings. One reader listens to it for the conversation's whole
life, so turns Claude starts on its own (a background task finishing) are
heard too. Everything it hears is translated into watch events, numbered,
and kept, so a watch that drops off can ask for what it missed.
"""

import asyncio
import time
import uuid
from typing import Callable, Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, ResultMessage

from watch_pc_controller.claude_bridge import PermissionBridge
from watch_pc_controller.claude_events import translate
from watch_pc_controller.claude_risk import classify

BUFFER_SIZE = 500

WATCH_PROMPT = """The user is talking to you by voice from an Apple Watch. They hear your reply; they do not read a terminal.
- Reply in spoken Hebrew, briefly: at most three sentences.
- No markdown, tables, lists or code in the reply. Code goes into files and is never read aloud.
- Name files by their short name (server.py), never by full path.
- Ask one question at a time. When there are clear options, use the AskUserQuestion tool.
- When a detail is long, say that it is in the conversation on the computer.
- When you finish a piece of work, end with one sentence saying what changed.
- Write the description of every command you run in Hebrew; the user sees it on the watch."""


class ConversationBusy(Exception):
    """Claude is still working on the previous message."""


class ConversationStartFailed(Exception):
    """Claude Code could not be started (not installed, not logged in, ...)."""


class ConversationBroken(Exception):
    """Claude Code stopped answering in this conversation; open it again."""


GONE_MESSAGE = "Claude Code הפסיק לענות בשיחה הזו. פתח אותה שוב."
MAX_READ_FAILURES = 3


async def _destructive_goes_to_the_watch(input_data, tool_use_id, context):
    """In acceptEdits mode Claude Code deletes files inside the project (rm) without
    asking anyone, so can_use_tool never hears of it. Destructive commands are
    sent back through the permission flow, where the watch asks for a long hold.

    (The Python SDK also needs some PreToolUse hook registered for can_use_tool
    to be consulted while streaming; this hook is that one.)"""
    tool = input_data.get("tool_name")
    if tool in ("Bash", "PowerShell") and classify(tool, input_data.get("tool_input") or {}) == "destructive":
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Destructive commands need the user's approval on the watch.",
        }}
    return {"continue_": True}


def build_options(project_path: str, session_id: Optional[str], can_use_tool) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=project_path,
        resume=session_id or None,
        permission_mode="acceptEdits",
        can_use_tool=can_use_tool,
        include_partial_messages=True,
        setting_sources=["user", "project", "local"],
        system_prompt={"type": "preset", "preset": "claude_code", "append": WATCH_PROMPT},
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_destructive_goes_to_the_watch])]},
    )


class Conversation:
    def __init__(self, cid: str, project: str, session_id: Optional[str], clock: Callable[[], float]):
        self.id = cid
        self.project = project
        self.session_id = session_id
        self.state = "idle"
        self.client = None
        self.bridge: Optional[PermissionBridge] = None
        self._clock = clock
        self.last_activity = clock()
        self._events: list[dict] = []
        self._seq = 0
        self._listeners: set[asyncio.Queue] = set()
        self._reader: Optional[asyncio.Task] = None
        self._closing = False
        self.alive = True

    # --------------------------------------------------------- events

    def publish(self, event: dict) -> None:
        self._seq += 1
        item = {"seq": self._seq, **event}
        self._events.append(item)
        del self._events[:-BUFFER_SIZE]
        self.last_activity = self._clock()
        kind = event.get("type")
        if kind == "session" and event.get("session_id"):
            self.session_id = event["session_id"]
        elif kind in ("approval", "question"):
            self.state = "waiting"
        elif kind in ("answered", "expired") and self.state == "waiting":
            # Claude can wait on two things at once; it is still waiting until both are answered.
            self.state = "waiting" if self.bridge and self.bridge.pending() else "working"
        for queue in list(self._listeners):
            queue.put_nowait(item)

    def replay(self, after: int) -> list[dict]:
        return [e for e in self._events if e["seq"] > after]

    def listen(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.add(queue)
        return queue

    def unlisten(self, queue: asyncio.Queue) -> None:
        self._listeners.discard(queue)

    # --------------------------------------------------------- talking

    def start(self) -> None:
        self._reader = asyncio.create_task(self._read())

    async def send(self, text: str) -> None:
        if not self.alive:
            raise ConversationBroken(GONE_MESSAGE)
        if self.state != "idle":
            raise ConversationBusy()
        self.state = "working"
        self.publish({"type": "you", "text": text})
        try:
            await self.client.query(text)
        except Exception as exc:          # the CLI is gone: say so, and do not stay "working" forever
            self.state = "idle"
            self.publish({"type": "error", "message": str(exc)})
            raise ConversationBroken(str(exc)) from exc

    async def _read(self) -> None:
        failures = 0
        cancelled = False
        try:
            while True:
                try:
                    async for message in self.client.receive_messages():
                        failures = 0
                        events = translate(message)
                        if self.state == "idle" and any(e["type"] != "rate_limit" for e in events):
                            self.state = "working"        # a turn Claude started on its own
                        for event in events:
                            self.publish(event)
                        if isinstance(message, ResultMessage):
                            self.state = "idle"
                            self.last_activity = self._clock()
                    break                                 # the stream ended: Claude Code exited
                except asyncio.CancelledError:            # closing or shutting down, not a failure
                    cancelled = True
                    raise
                except Exception as exc:                  # one bad message loses the turn, not the conversation
                    failures += 1
                    self.state = "idle"
                    self.publish({"type": "error", "message": str(exc)})
                    if failures >= MAX_READ_FAILURES:
                        break
        finally:
            self.alive = False
            self.state = "idle"
            if not (self._closing or cancelled):
                self.bridge.cancel_all()
                self.publish({"type": "error", "message": GONE_MESSAGE})

    async def interrupt(self) -> None:
        self.bridge.cancel_all()
        await self.client.interrupt()

    async def close(self) -> None:
        self._closing = True
        self.alive = False
        self.bridge.cancel_all()
        try:
            await self.client.disconnect()
        finally:
            if self._reader and not self._reader.done():
                self._reader.cancel()


class ConversationManager:
    def __init__(self, client_factory=ClaudeSDKClient, audit: Callable[[dict], None] = lambda entry: None,
                 idle_close_s: float = 900, clock: Callable[[], float] = time.monotonic):
        self._client_factory = client_factory
        self._audit = audit
        self._idle_close_s = idle_close_s
        self._clock = clock
        self._conversations: dict[str, Conversation] = {}

    async def open(self, project_path: str, session_id: Optional[str] = None) -> Conversation:
        await self.close_idle()
        for conv in self._conversations.values():     # the same session is already open: reuse it
            if session_id and conv.alive and conv.project == project_path and conv.session_id == session_id:
                return conv
        conv = Conversation(uuid.uuid4().hex[:12], project_path, session_id, self._clock)
        conv.bridge = PermissionBridge(emit=conv.publish, audit=self._audit, project=project_path)
        conv.client = self._client_factory(build_options(project_path, session_id, conv.bridge.can_use_tool))
        try:
            await conv.client.connect()
        except Exception as exc:
            raise ConversationStartFailed(str(exc)) from exc
        self._conversations[conv.id] = conv
        conv.start()
        return conv

    def get(self, cid: str) -> Conversation:
        return self._conversations[cid]

    def summary(self) -> list[dict]:
        return [
            {"id": c.id, "project": c.project, "session_id": c.session_id, "state": c.state, "waiting": c.state == "waiting"}
            for c in self._conversations.values()
        ]

    def waiting_projects(self) -> set[str]:
        return {c.project for c in self._conversations.values() if c.state == "waiting"}

    async def close(self, cid: str) -> None:
        conv = self._conversations.pop(cid)
        await conv.close()

    async def close_idle(self) -> None:
        now = self._clock()
        stale = [cid for cid, c in self._conversations.items()
                 if not c.alive or (c.state == "idle" and now - c.last_activity > self._idle_close_s)]
        for cid in stale:
            await self.close(cid)

    async def close_all(self) -> None:
        for cid in list(self._conversations):
            await self.close(cid)
