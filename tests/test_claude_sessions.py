# -*- coding: utf-8 -*-
"""Conversations: send, stream, wait for the watch, replay after a drop."""

import asyncio

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultAllow,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from watch_pc_controller.claude_sessions import (
    WATCH_PROMPT,
    ConversationBusy,
    ConversationManager,
    ConversationStartFailed,
    build_options,
)


def delta(text):
    return StreamEvent(uuid="u", session_id="s1", event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


def result(text="סיימתי"):
    return ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9, is_error=False, num_turns=1, session_id="s1", result=text)


_END = object()


class FakeClient:
    """Stands in for ClaudeSDKClient.

    Like the real one, it has a single message stream for its whole life. Each
    query adds its scripted turn to that stream; push() adds a turn Claude
    starts on its own (a background task finishing); exit() is the CLI dying.
    """

    def __init__(self, options, turns, fail_connect=False, fail_query=False):
        self.options = options
        self.turns = list(turns)
        self.queries = []
        self.fail_connect = fail_connect
        self.fail_query = fail_query
        self.interrupted = False
        self.closed = False
        self._inbox = asyncio.Queue()

    async def connect(self):
        if self.fail_connect:
            raise RuntimeError("Claude Code is not logged in")

    async def query(self, text):
        if self.fail_query:
            raise RuntimeError("Claude Code is not running")
        self.queries.append(text)
        self.push(self.turns.pop(0) if self.turns else [])

    def push(self, turn):
        for item in turn:
            self._inbox.put_nowait(item)

    def exit(self):
        self._inbox.put_nowait(_END)

    async def receive_messages(self):
        while True:
            item = await self._inbox.get()
            if item is _END:
                return
            if callable(item):
                item = await item(self)
            if item is not None:
                yield item

    async def receive_response(self):
        async for message in self.receive_messages():
            yield message
            if isinstance(message, ResultMessage):
                return

    async def interrupt(self):
        self.interrupted = True

    async def disconnect(self):
        self.closed = True
        self.exit()


def manager_with(turns, **kw):
    made = []

    def factory(options):
        client = FakeClient(options, turns, **kw)
        made.append(client)
        return client

    return ConversationManager(client_factory=factory), made


async def settle(conv):
    for _ in range(200):
        if conv.state == "idle":
            return
        await asyncio.sleep(0.005)
    raise AssertionError("conversation never went idle")


def test_build_options_uses_the_users_own_setup():
    opts = build_options(r"D:\Projects\Robox", "s1", can_use_tool=lambda *a: None)
    assert opts.cwd == r"D:\Projects\Robox"
    assert opts.resume == "s1"
    assert opts.permission_mode == "acceptEdits"
    assert opts.setting_sources == ["user", "project", "local"]
    assert opts.include_partial_messages is True
    assert opts.system_prompt == {"type": "preset", "preset": "claude_code", "append": WATCH_PROMPT}
    assert "PreToolUse" in opts.hooks


def _pre_tool_use(tool, tool_input):
    hook = build_options("D:/p", None, can_use_tool=None).hooks["PreToolUse"][0].hooks[0]
    data = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "tool_use_id": "t1"}
    return asyncio.run(hook(data, "t1", {"signal": None}))


@pytest.mark.parametrize("tool,command", [
    ("Bash", "rm junk2.txt"),                      # acceptEdits lets Claude Code run this without asking
    ("Bash", "rm -rf build"),
    ("PowerShell", "Remove-Item junk1.txt"),
    ("Bash", "git push star main"),
])
def test_destructive_commands_are_always_sent_to_the_watch(tool, command):
    out = _pre_tool_use(tool, {"command": command})
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


@pytest.mark.parametrize("tool,tool_input", [
    ("Bash", {"command": "git status"}),
    ("Bash", {"command": "npm install"}),
    ("Edit", {"file_path": "D:/p/a.py"}),
])
def test_other_requests_follow_the_normal_flow(tool, tool_input):
    assert "hookSpecificOutput" not in _pre_tool_use(tool, tool_input)


def test_new_conversation_does_not_resume():
    assert build_options("D:/p", None, can_use_tool=None).resume is None


def test_send_streams_events_in_order():
    async def scenario():
        mgr, made = manager_with([[SystemMessage(subtype="init", data={"session_id": "s1", "model": "m"}),
                                   delta("שלום "), delta("עומרי"), result()]])
        conv = await mgr.open("D:/p")
        await conv.send("היי")
        await settle(conv)
        return conv, made[0]
    conv, client = asyncio.run(scenario())
    types = [e["type"] for e in conv.replay(0)]
    assert types == ["you", "session", "text", "text", "done"]
    assert [e["seq"] for e in conv.replay(0)] == [1, 2, 3, 4, 5]
    assert conv.session_id == "s1"
    assert client.queries == ["היי"]


def test_events_after_replays_only_newer():
    async def scenario():
        mgr, _ = manager_with([[delta("a"), delta("b"), result()]])
        conv = await mgr.open("D:/p")
        await conv.send("x")
        await settle(conv)
        return conv
    conv = asyncio.run(scenario())
    assert [e["seq"] for e in conv.replay(2)] == [3, 4]


def test_send_while_working_is_refused():
    async def scenario():
        gate = asyncio.Event()

        async def wait_for_gate(client):
            await gate.wait()
            return result()

        mgr, _ = manager_with([[wait_for_gate]])
        conv = await mgr.open("D:/p")
        await conv.send("first")
        with pytest.raises(ConversationBusy):
            await conv.send("second")
        gate.set()
        await settle(conv)
    asyncio.run(scenario())


def test_approval_round_trip_marks_waiting_then_working():
    async def scenario():
        states = []

        async def ask_permission(client):
            states.append(conv_ref[0].state)
            res = await client.options.can_use_tool("Bash", {"command": "npm install"}, ToolPermissionContext())
            states.append(("result", type(res).__name__))
            return UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok", is_error=False)])

        mgr, _ = manager_with([[AssistantMessage(content=[ToolUseBlock(id="t1", name="Bash", input={"command": "npm install"})], model="m"),
                                ask_permission, result()]])
        conv = await mgr.open("D:/p")
        conv_ref[0] = conv
        await conv.send("תתקין")
        for _ in range(200):
            if conv.state == "waiting":
                break
            await asyncio.sleep(0.005)
        assert conv.state == "waiting"
        assert mgr.waiting_projects() == {"D:/p"}
        request = next(e for e in conv.replay(0) if e["type"] == "approval")
        assert conv.bridge.answer(request["id"], {"allow": True})
        await settle(conv)
        return states

    conv_ref = [None]
    states = asyncio.run(scenario())
    assert states == ["working", ("result", "PermissionResultAllow")]


def test_open_reports_a_failed_start():
    async def scenario():
        mgr, _ = manager_with([], fail_connect=True)
        with pytest.raises(ConversationStartFailed) as err:
            await mgr.open("D:/p")
        return str(err.value)
    assert "not logged in" in asyncio.run(scenario())


def test_an_error_while_streaming_is_reported_and_frees_the_conversation():
    async def scenario():
        async def explode(client):
            raise RuntimeError("stream broke")

        mgr, _ = manager_with([[explode], [result()]])
        conv = await mgr.open("D:/p")
        await conv.send("x")
        await settle(conv)
        await conv.send("again")          # idle again, so this is accepted
        await settle(conv)
        return conv
    conv = asyncio.run(scenario())
    errors = [e for e in conv.replay(0) if e["type"] == "error"]
    assert errors and "stream broke" in errors[0]["message"]


def test_interrupt_denies_pending_and_tells_the_client():
    async def scenario():
        async def ask(client):
            return await client.options.can_use_tool("Bash", {"command": "npm install"}, ToolPermissionContext()) and None

        mgr, made = manager_with([[ask, result()]])
        conv = await mgr.open("D:/p")
        await conv.send("x")
        for _ in range(200):
            if conv.state == "waiting":
                break
            await asyncio.sleep(0.005)
        await conv.interrupt()
        await settle(conv)
        return made[0]
    assert asyncio.run(scenario()).interrupted is True


def test_listeners_receive_new_events():
    async def scenario():
        mgr, _ = manager_with([[delta("a"), result()]])
        conv = await mgr.open("D:/p")
        queue = conv.listen()
        await conv.send("x")
        got = [await asyncio.wait_for(queue.get(), 1) for _ in range(3)]
        conv.unlisten(queue)
        return [e["type"] for e in got]
    assert asyncio.run(scenario()) == ["you", "text", "done"]


def test_idle_conversations_are_closed():
    async def scenario():
        now = [0.0]
        made = []

        def factory(options):
            made.append(FakeClient(options, []))
            return made[-1]

        mgr = ConversationManager(client_factory=factory, idle_close_s=900, clock=lambda: now[0])
        conv = await mgr.open("D:/p")
        now[0] = 901
        await mgr.close_idle()
        return mgr, conv, made[0]
    mgr, conv, client = asyncio.run(scenario())
    assert client.closed is True
    with pytest.raises(KeyError):
        mgr.get(conv.id)


def test_summary_lists_open_conversations():
    async def scenario():
        mgr, _ = manager_with([])
        conv = await mgr.open("D:/p", session_id="s9")
        return mgr.summary(), conv.id
    summary, cid = asyncio.run(scenario())
    assert summary == [{"id": cid, "project": "D:/p", "session_id": "s9", "state": "idle", "waiting": False}]


def test_a_turn_claude_starts_by_itself_is_heard_and_the_next_reply_is_not_off_by_one():
    """A finished background task wakes Claude into a turn nobody sent."""
    async def scenario():
        mgr, made = manager_with([[delta("הנה"), result("התשובה שלך")]])
        conv = await mgr.open("D:/p")
        made[0].push([SystemMessage(subtype="init", data={"session_id": "s1", "model": "m"}),
                      delta("המשימה ברקע הסתיימה"), result("המשימה ברקע הסתיימה")])
        for _ in range(200):
            if any(e["type"] == "done" for e in conv.replay(0)):
                break
            await asyncio.sleep(0.005)
        heard = [e["type"] for e in conv.replay(0)]
        await settle(conv)
        await conv.send("מה המצב?")
        for _ in range(200):
            if [e["type"] for e in conv.replay(0)].count("done") == 2:
                break
            await asyncio.sleep(0.005)
        await settle(conv)
        return heard, conv
    heard, conv = asyncio.run(scenario())
    assert heard == ["session", "text", "done"]
    assert [e["text"] for e in conv.replay(0) if e["type"] == "done"] == ["המשימה ברקע הסתיימה", "התשובה שלך"]


def test_waiting_lasts_while_any_request_is_open():
    async def scenario():
        async def ask_twice(fake):
            ctx = ToolPermissionContext()
            await asyncio.gather(fake.options.can_use_tool("Bash", {"command": "npm install"}, ctx),
                                 fake.options.can_use_tool("Bash", {"command": "pip install x"}, ctx))
            return None

        mgr, _ = manager_with([[ask_twice, result()]])
        conv = await mgr.open("D:/p")
        await conv.send("תתקין")
        for _ in range(200):
            if len(conv.bridge.pending()) == 2:
                break
            await asyncio.sleep(0.005)
        first, second = [e for e in conv.replay(0) if e["type"] == "approval"]
        conv.bridge.answer(first["id"], {"allow": True})
        after_first = (conv.state, mgr.waiting_projects())
        conv.bridge.answer(second["id"], {"allow": True})
        after_second = conv.state
        await settle(conv)
        return after_first, after_second
    after_first, after_second = asyncio.run(scenario())
    assert after_first == ("waiting", {"D:/p"})
    assert after_second == "working"


def test_a_failed_send_frees_the_conversation():
    from watch_pc_controller.claude_sessions import ConversationBroken

    async def scenario():
        mgr, _ = manager_with([], fail_query=True)
        conv = await mgr.open("D:/p")
        with pytest.raises(ConversationBroken):
            await conv.send("x")
        return conv
    conv = asyncio.run(scenario())
    assert conv.state == "idle"
    assert conv.replay(0)[-1]["type"] == "error"


def test_when_claude_code_exits_the_conversation_says_so_and_refuses_messages():
    from watch_pc_controller.claude_sessions import ConversationBroken

    async def scenario():
        mgr, made = manager_with([])
        conv = await mgr.open("D:/p")
        made[0].exit()
        for _ in range(200):
            if not conv.alive:
                break
            await asyncio.sleep(0.005)
        with pytest.raises(ConversationBroken):
            await conv.send("x")
        await mgr.close_idle()                      # a dead conversation is cleaned up at once
        return mgr, conv
    mgr, conv = asyncio.run(scenario())
    assert conv.replay(0)[-1]["type"] == "error"
    assert mgr.summary() == []


def test_close_all_closes_every_conversation():
    async def scenario():
        mgr, made = manager_with([])
        await mgr.open("D:/a")
        await mgr.open("D:/b")
        await mgr.close_all()
        return mgr, made
    mgr, made = asyncio.run(scenario())
    assert mgr.summary() == [] and all(c.closed for c in made)
