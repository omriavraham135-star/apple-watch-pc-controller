# -*- coding: utf-8 -*-
"""What the watch hears about while Claude works."""

from claude_agent_sdk import (
    AssistantMessage,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
import pytest
from claude_agent_sdk.types import RateLimitInfo, ThinkingBlock

from watch_pc_controller.claude_events import tool_label, translate


def test_init_announces_the_session():
    events = translate(SystemMessage(subtype="init", data={"session_id": "s1", "model": "claude-opus-5-5"}))
    assert events == [{"type": "session", "session_id": "s1", "model": "claude-opus-5-5"}]


def test_other_system_messages_are_quiet():
    assert translate(SystemMessage(subtype="hook_started", data={})) == []


def test_text_deltas_stream():
    event = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "שלום"}}
    assert translate(StreamEvent(uuid="u", session_id="s", event=event)) == [{"type": "text", "delta": "שלום"}]


def test_thinking_deltas_are_not_spoken():
    event = {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hmm"}}
    assert translate(StreamEvent(uuid="u", session_id="s", event=event)) == []


def test_assistant_tool_use_becomes_a_labelled_tool_event():
    msg = AssistantMessage(content=[ToolUseBlock(id="t1", name="Read", input={"file_path": r"D:\p\server.py"})], model="m")
    assert translate(msg) == [{"type": "tool", "id": "t1", "name": "Read", "label": "קורא את server.py"}]


def test_assistant_text_block_is_kept_for_reconciliation():
    msg = AssistantMessage(content=[TextBlock(text="סיימתי"), ThinkingBlock(thinking="x", signature="y")], model="m")
    assert translate(msg) == [{"type": "text_block", "text": "סיימתי"}]


def test_not_logged_in_says_so_in_hebrew():
    msg = AssistantMessage(content=[TextBlock(text="Invalid API key · Please run /login")], model="", error="authentication_failed")
    assert translate(msg) == [{"type": "error", "code": "authentication_failed",
                               "message": "צריך להתחבר ל‑Claude Code במחשב"}]


@pytest.mark.parametrize("code", ["billing_error", "rate_limit", "invalid_request", "server_error", "unknown"])
def test_every_assistant_error_becomes_an_error_event(code):
    [event] = translate(AssistantMessage(content=[TextBlock(text="x")], model="", error=code))
    assert event["type"] == "error" and event["code"] == code and event["message"]


def test_subagent_messages_are_quiet():
    msg = AssistantMessage(content=[TextBlock(text="inner")], model="m", parent_tool_use_id="t9")
    assert translate(msg) == []


def test_tool_result_marks_the_tool_done():
    msg = UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok", is_error=False)])
    assert translate(msg) == [{"type": "tool_done", "id": "t1", "ok": True}]


def test_tool_error_is_reported():
    msg = UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="boom", is_error=True)])
    assert translate(msg) == [{"type": "tool_done", "id": "t1", "ok": False}]


def test_plain_user_text_is_quiet():
    assert translate(UserMessage(content="hello")) == []


def test_result_ends_the_turn():
    msg = ResultMessage(subtype="success", duration_ms=4344, duration_api_ms=4000, is_error=False,
                        num_turns=1, session_id="s1", result="שלום")
    assert translate(msg) == [{"type": "done", "session_id": "s1", "ok": True, "text": "שלום",
                               "duration_ms": 4344, "interrupted": False}]


def test_interrupted_result_says_so():
    msg = ResultMessage(subtype="error_during_execution", duration_ms=1, duration_api_ms=1, is_error=True,
                        num_turns=1, session_id="s1", terminal_reason="aborted_streaming")
    assert translate(msg)[0]["interrupted"] is True


def test_rate_limit_is_passed_on():
    msg = RateLimitEvent(rate_limit_info=RateLimitInfo(status="rejected", resets_at=1790000000), uuid="u", session_id="s")
    assert translate(msg) == [{"type": "rate_limit", "status": "rejected", "resets_at": 1790000000}]


def test_an_allowed_rate_limit_is_quiet():
    msg = RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed", resets_at=1790000000), uuid="u", session_id="s")
    assert translate(msg) == []


def test_tool_labels():
    assert tool_label("Edit", {"file_path": "C:/x/watch-ui.js"}) == "עורך את watch-ui.js"
    assert tool_label("Write", {"file_path": "a/b/new.py"}) == "כותב את new.py"
    assert tool_label("Bash", {"command": "py -m pytest", "description": "מריץ את הבדיקות"}) == "מריץ את הבדיקות"
    assert tool_label("Bash", {"command": "npm install"}) == "מריץ npm install"
    assert tool_label("Grep", {"pattern": "def main"}) == "מחפש “def main”"
    assert tool_label("Unknown", {}) == "Unknown"
