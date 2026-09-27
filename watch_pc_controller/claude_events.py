"""What the watch hears about while Claude works.

Claude Code's SDK speaks in rich message objects. The watch needs a few plain
events: a session began, words arrived, a tool started or finished, the turn
ended. Anything else stays on the PC.
"""

import os

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

_INTERRUPTED = {"aborted_streaming", "aborted_tools"}

# Claude Code reports these on the reply itself, with English text meant for a
# terminal. The watch says what to do instead (spec section 7).
_ERRORS = {
    "authentication_failed": "צריך להתחבר ל‑Claude Code במחשב",
    "billing_error": "יש בעיה בחיוב של חשבון Claude. בדוק במחשב",
    "rate_limit": "הגעת למגבלת השימוש של Claude. נסה שוב מאוחר יותר",
    "invalid_request": "Claude לא הצליח לטפל בבקשה הזו",
    "server_error": "השרתים של Claude לא זמינים כרגע. נסה שוב עוד מעט",
    "unknown": "משהו השתבש אצל Claude. הפרטים בשיחה במחשב",
}


def _short(path) -> str:
    return os.path.basename(str(path).replace("\\", "/")) if path else ""


def tool_label(name: str, tool_input: dict) -> str:
    """A short Hebrew line for 'what Claude is doing now'."""
    i = tool_input or {}
    if name == "Read":
        return f"קורא את {_short(i.get('file_path'))}"
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return f"עורך את {_short(i.get('file_path') or i.get('notebook_path'))}"
    if name == "Write":
        return f"כותב את {_short(i.get('file_path'))}"
    if name in ("Bash", "PowerShell"):
        return i.get("description") or f"מריץ {str(i.get('command', ''))[:40]}"
    if name == "Grep":
        return f"מחפש “{str(i.get('pattern', ''))[:30]}”"
    if name == "Glob":
        return f"מחפש קבצים {i.get('pattern', '')}"
    if name == "WebSearch":
        return f"מחפש ברשת: {str(i.get('query', ''))[:30]}"
    if name == "WebFetch":
        return "קורא דף אינטרנט"
    if name in ("Task", "Agent"):
        return "מפעיל סוכן עזר"
    if name == "TodoWrite":
        return "מעדכן את רשימת המשימות"
    if name == "AskUserQuestion":
        return "שואל אותך שאלה"
    return name


def translate(message) -> list[dict]:
    if isinstance(message, SystemMessage):
        if message.subtype == "init":
            return [{"type": "session", "session_id": message.data.get("session_id"), "model": message.data.get("model")}]
        return []

    if isinstance(message, StreamEvent):
        event = message.event or {}
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            return [{"type": "text", "delta": delta.get("text", "")}]
        return []

    if isinstance(message, AssistantMessage):
        if message.parent_tool_use_id:          # a subagent's inner turns stay on the PC
            return []
        if message.error:
            return [{"type": "error", "code": message.error, "message": _ERRORS.get(message.error, _ERRORS["unknown"])}]
        events = []
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                events.append({"type": "tool", "id": block.id, "name": block.name, "label": tool_label(block.name, block.input)})
            elif isinstance(block, TextBlock):
                events.append({"type": "text_block", "text": block.text})
        return events

    if isinstance(message, UserMessage):
        if not isinstance(message.content, list):
            return []
        return [
            {"type": "tool_done", "id": block.tool_use_id, "ok": not bool(block.is_error)}
            for block in message.content
            if isinstance(block, ToolResultBlock)
        ]

    if isinstance(message, ResultMessage):
        return [{
            "type": "done",
            "session_id": message.session_id,
            "ok": not message.is_error,
            "text": message.result or "",
            "duration_ms": message.duration_ms,
            "interrupted": message.terminal_reason in _INTERRUPTED,
        }]

    if isinstance(message, RateLimitEvent):
        info = message.rate_limit_info
        if info.status == "allowed":            # arrives every turn; only warnings matter
            return []
        return [{"type": "rate_limit", "status": info.status, "resets_at": info.resets_at}]

    return []
