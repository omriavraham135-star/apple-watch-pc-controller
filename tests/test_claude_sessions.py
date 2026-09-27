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


class FakeClient:
    """Plays back one scripted list of messages per query."""

    def __init__(self, options, turns, fail_connect=False):
        self.options = options
        self.turns = list(turns)
        self.queries = []
        self.fail_connect = fail_connect
        self.interrupted = False
        self.closed = False

    async def connect(self):
        if self.fail_connect:
            raise RuntimeError("Claude Code is not logged in")

    async def query(self, text):
        self.queries.append(text)

    async def receive_response(self):
        for item in (self.turns.pop(0) if self.turns else []):
            if callable(item):
                item = await item(self)
            if item is not None:
                yield item

    async def interrupt(self):
        self.interrupted = True

    async def disconnect(self):
        self.closed = True


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
