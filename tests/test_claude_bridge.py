# -*- coding: utf-8 -*-
"""Claude's questions and approvals wait for the watch, and only for the watch."""

import asyncio
import json

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext
from claude_agent_sdk.types import PermissionRuleValue, PermissionUpdate

from watch_pc_controller.claude_bridge import AuditLog, PermissionBridge


def make_bridge(timeout_s=5.0):
    events, audits = [], []
    bridge = PermissionBridge(emit=events.append, audit=audits.append, timeout_s=timeout_s, project="Robox")
    return bridge, events, audits


def run(coro):
    return asyncio.run(coro)


def test_read_only_command_passes_without_asking():
    bridge, events, _ = make_bridge()
    result = run(bridge.can_use_tool("Bash", {"command": "git status"}, ToolPermissionContext()))
    assert isinstance(result, PermissionResultAllow)
    assert events == []


def test_a_command_that_ran_without_asking_is_still_in_the_audit_log():
    bridge, _, audits = make_bridge()
    run(bridge.can_use_tool("Bash", {"command": "git status"}, ToolPermissionContext()))
    assert audits == [{"project": "Robox", "tool": "Bash", "command": "git status", "risk": "read", "decision": "auto"}]


@pytest.mark.parametrize("payload", [{"allow": "false"}, {"allow": "true"}, {"allow": 1}, {}, {"allow": None}])
def test_only_a_real_yes_approves(payload):
    async def scenario():
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "npm install"}, ToolPermissionContext()))
        await asyncio.sleep(0)
        bridge.answer(events[0]["id"], payload)
        return await task
    assert isinstance(run(scenario()), PermissionResultDeny)


def test_a_destructive_command_is_never_remembered():
    """It is always sent back to the watch, so 'always' would be a promise we do not keep."""
    rule = PermissionUpdate(type="addRules", rules=[PermissionRuleValue(tool_name="Bash", rule_content="rm junk.txt")],
                            behavior="allow", destination="localSettings")

    async def scenario():
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "rm junk.txt"}, ToolPermissionContext(suggestions=[rule])))
        await asyncio.sleep(0)
        request = events[0]
        bridge.answer(request["id"], {"allow": True, "always": True})
        return request, await task
    request, result = run(scenario())
    assert request["can_remember"] is False and result.updated_permissions is None


def test_always_never_widens_the_folders_claude_can_reach():
    """Spec 3.3: Claude stays in the project; 'always' may only remember a rule."""
    widen = PermissionUpdate(type="addDirectories", directories=["C:\\Users"], destination="localSettings")
    rule = PermissionUpdate(type="addRules", rules=[PermissionRuleValue(tool_name="Read", rule_content="C:\\Users\\**")],
                            behavior="allow", destination="localSettings")

    async def scenario(suggestions):
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "npm test"}, ToolPermissionContext(suggestions=suggestions)))
        await asyncio.sleep(0)
        request = events[0]
        bridge.answer(request["id"], {"allow": True, "always": True})
        return request, await task

    request, result = run(scenario([widen]))
    assert request["can_remember"] is False and result.updated_permissions is None
    request, result = run(scenario([widen, rule]))
    assert result.updated_permissions == [rule]


def test_approval_waits_and_allows():
    async def scenario():
        bridge, events, audits = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "npm install", "description": "מתקין"}, ToolPermissionContext()))
        await asyncio.sleep(0)
        request = events[0]
        assert request["type"] == "approval" and request["risk"] == "normal" and request["hold_seconds"] == 2
        assert request["command"] == "npm install" and request["description"] == "מתקין"
        assert bridge.answer(request["id"], {"allow": True}) is True
        result = await task
        return result, events, audits
    result, events, audits = run(scenario())
    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input == {"command": "npm install", "description": "מתקין"}
    assert events[-1] == {"type": "answered", "id": events[0]["id"]}
    assert audits[0]["decision"] == "allowed" and audits[0]["project"] == "Robox"


def test_destructive_asks_for_a_longer_hold():
    async def scenario():
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "git push star main"}, ToolPermissionContext()))
        await asyncio.sleep(0)
        bridge.answer(events[0]["id"], {"allow": False, "reason": "עוד לא"})
        return events[0], await task
    request, result = run(scenario())
    assert request["risk"] == "destructive" and request["hold_seconds"] == 3
    assert isinstance(result, PermissionResultDeny)
    assert "עוד לא" in result.message


def test_always_passes_back_only_local_settings_suggestions():
    local = PermissionUpdate(type="addRules", rules=[PermissionRuleValue(tool_name="Bash", rule_content="npm test")],
                             behavior="allow", destination="localSettings")
    user = PermissionUpdate(type="addRules", rules=[PermissionRuleValue(tool_name="Bash")],
                            behavior="allow", destination="userSettings")

    async def scenario():
        bridge, events, _ = make_bridge()
        ctx = ToolPermissionContext(suggestions=[user, local])
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "npm test"}, ctx))
        await asyncio.sleep(0)
        assert events[0]["can_remember"] is True
        bridge.answer(events[0]["id"], {"allow": True, "always": True})
        return await task
    result = run(scenario())
    assert result.updated_permissions == [local]


def test_question_returns_answers_in_the_sdk_shape():
    questions = [{"question": "איך להציג?", "header": "תצוגה", "multiSelect": False,
                  "options": [{"label": "טבעת", "description": "d1"}, {"label": "מספרים", "description": "d2"}]}]

    async def scenario():
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("AskUserQuestion", {"questions": questions}, ToolPermissionContext()))
        await asyncio.sleep(0)
        request = events[0]
        assert request["type"] == "question"
        assert request["questions"][0] == {"question": "איך להציג?", "header": "תצוגה", "multi": False,
                                          "options": [{"label": "טבעת", "description": "d1"},
                                                      {"label": "מספרים", "description": "d2"}]}
        bridge.answer(request["id"], {"answers": {"איך להציג?": "טבעת"}})
        return await task
    result = run(scenario())
    assert result.updated_input == {"questions": questions, "answers": {"איך להציג?": "טבעת"}}


def test_free_text_reply_to_a_question():
    async def scenario():
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("AskUserQuestion", {"questions": []}, ToolPermissionContext()))
        await asyncio.sleep(0)
        bridge.answer(events[0]["id"], {"answers": {}, "response": "תעשה מה שנראה לך"})
        return await task
    assert run(scenario()).updated_input["response"] == "תעשה מה שנראה לך"


def test_unanswered_request_expires_and_interrupts():
    async def scenario():
        bridge, events, audits = make_bridge(timeout_s=0.05)
        result = await bridge.can_use_tool("Bash", {"command": "npm install"}, ToolPermissionContext())
        return result, events, audits
    result, events, audits = run(scenario())
    assert isinstance(result, PermissionResultDeny) and result.interrupt is True
    assert events[-1]["type"] == "expired"
    assert audits[0]["decision"] == "expired"


def test_two_requests_resolve_independently():
    async def scenario():
        bridge, events, _ = make_bridge()
        a = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "npm install"}, ToolPermissionContext()))
        b = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "pip install x"}, ToolPermissionContext()))
        await asyncio.sleep(0)
        first, second = events[0], events[1]
        assert {r["id"] for r in bridge.pending()} == {first["id"], second["id"]}
        bridge.answer(second["id"], {"allow": False})
        bridge.answer(first["id"], {"allow": True})
        return await a, await b
    ra, rb = run(scenario())
    assert isinstance(ra, PermissionResultAllow) and isinstance(rb, PermissionResultDeny)


def test_answering_an_unknown_request_is_refused():
    bridge, _, _ = make_bridge()
    assert bridge.answer("nope", {"allow": True}) is False


def test_cancel_all_denies_what_is_waiting():
    async def scenario():
        bridge, events, _ = make_bridge()
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "npm install"}, ToolPermissionContext()))
        await asyncio.sleep(0)
        bridge.cancel_all()
        return await task
    assert isinstance(run(scenario()), PermissionResultDeny)


def test_audit_log_appends_json_lines(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    log.record({"decision": "allowed", "command": "npm test"})
    log.record({"decision": "denied", "command": "git push"})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["decision"] for l in lines] == ["allowed", "denied"]
    assert log.recent(1)[0]["command"] == "git push"
    assert "ts" in log.recent(1)[0]


# Spec 1.7: work outside the project folder always waits for approval, even a read.

PROJECT = r"D:\Projects\Robox"


def make_project_bridge():
    events = []
    return PermissionBridge(emit=events.append, audit=lambda entry: None, timeout_s=5.0, project=PROJECT), events


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": r"C:\Users\omria\.ssh\id_rsa"}),
    ("Read", {"file_path": r"D:\Projects\Robox-other\notes.txt"}),
    ("Grep", {"pattern": "password", "path": "C:\\Users"}),
    ("Bash", {"command": r"cat C:\Users\omria\.ssh\id_rsa"}),
    ("PowerShell", {"command": r"Get-Content ..\..\secrets.txt"}),
    ("Bash", {"command": "ls ~"}),
    ("Bash", {"command": "cat /c/Users/omria/.ssh/id_rsa"}),           # Git Bash spelling of C:\
    ("Bash", {"command": "cat $HOME/.ssh/id_rsa"}),
    ("PowerShell", {"command": r"Get-Content $env:USERPROFILE\.ssh\id_rsa"}),
    ("PowerShell", {"command": "Get-ChildItem Env:"}),                  # PowerShell drives
    ("PowerShell", {"command": r"Get-ChildItem HKLM:\Software"}),
])
def test_reading_outside_the_project_asks(tool, tool_input):
    async def scenario():
        bridge, events = make_project_bridge()
        task = asyncio.create_task(bridge.can_use_tool(tool, tool_input, ToolPermissionContext()))
        await asyncio.sleep(0)
        assert events and events[0]["type"] == "approval"
        assert events[0]["risk"] == "normal" and events[0]["hold_seconds"] == 2
        bridge.answer(events[0]["id"], {"allow": False})
        return await task
    assert isinstance(run(scenario()), PermissionResultDeny)


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": PROJECT + r"\watch_pc_controller\server.py"}),
    ("Grep", {"pattern": "def main", "path": "watch_pc_controller"}),
    ("Bash", {"command": r"cat D:\Projects\Robox\README.md"}),
    ("Bash", {"command": "git log --oneline -5"}),
])
def test_reading_inside_the_project_passes(tool, tool_input):
    bridge, events = make_project_bridge()
    result = run(bridge.can_use_tool(tool, tool_input, ToolPermissionContext()))
    assert isinstance(result, PermissionResultAllow) and events == []


def test_a_blocked_path_always_asks():
    async def scenario():
        bridge, events = make_project_bridge()
        ctx = ToolPermissionContext(blocked_path=r"C:\Windows")
        task = asyncio.create_task(bridge.can_use_tool("Bash", {"command": "git status"}, ctx))
        await asyncio.sleep(0)
        assert events[0]["type"] == "approval"
        bridge.answer(events[0]["id"], {"allow": True})
        return await task
    assert isinstance(run(scenario()), PermissionResultAllow)
