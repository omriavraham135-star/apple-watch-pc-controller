# -*- coding: utf-8 -*-
"""The HTTP face of the Claude engine."""

import asyncio
import json

import httpx
import pytest

from watch_pc_controller import claude_api, server
from watch_pc_controller.claude_sessions import ConversationManager
from tests.test_claude_sessions import FakeClient, delta, result

LOCAL = "127.0.0.1"


@pytest.fixture
def roots(tmp_path, monkeypatch):
    (tmp_path / "Projects" / "Robox").mkdir(parents=True)
    monkeypatch.setattr(claude_api, "project_roots", lambda: [str(tmp_path / "Projects")])
    monkeypatch.setattr(claude_api, "list_conversations", lambda path: [{"session_id": "s1", "title": "חיישנים", "last_modified": 5}])
    monkeypatch.setattr(claude_api, "latest_session_id", lambda path: "s1")
    monkeypatch.setattr(claude_api, "latest_session_time", lambda path: 5)
    return tmp_path


@pytest.fixture
def turns(monkeypatch):
    script = []
    monkeypatch.setattr(claude_api, "_manager", ConversationManager(client_factory=lambda opts: FakeClient(opts, script)))
    return script


def with_client(scenario):
    """Run a scenario against the app on one event loop, like the real server."""
    async def go():
        transport = httpx.ASGITransport(app=server.app, client=(LOCAL, 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://pc") as client:
            return await scenario(client)
    return asyncio.run(go())


def call(method, path, json_body=None, params=None):
    return with_client(lambda client: client.request(method, path, json=json_body, params=params))


def test_projects_are_listed(roots, turns):
    res = call("GET", "/api/claude/projects")
    assert res.status_code == 200
    assert res.json()["projects"] == [{"name": "Robox", "last_activity": 5, "waiting": False}]


def test_create_project(roots, turns):
    assert call("POST", "/api/claude/projects", {"name": "portfolio"}).status_code == 201
    assert call("POST", "/api/claude/projects", {"name": "portfolio"}).status_code == 409
    assert call("POST", "/api/claude/projects", {"name": "../evil"}).status_code == 422


def test_conversations_of_a_project(roots, turns):
    assert call("GET", "/api/claude/projects/Robox/conversations").json()["conversations"][0]["title"] == "חיישנים"
    assert call("GET", "/api/claude/projects/Nope/conversations").status_code == 404


def test_open_continues_the_latest_session_by_default(roots, turns):
    res = call("POST", "/api/claude/conversations", {"project": "Robox"})
    assert res.status_code == 200 and res.json()["session_id"] == "s1"


def test_open_new_starts_fresh(roots, turns):
    assert call("POST", "/api/claude/conversations", {"project": "Robox", "new": True}).json()["session_id"] is None


def test_open_unknown_project(roots, turns):
    assert call("POST", "/api/claude/conversations", {"project": "Nope"}).status_code == 404


def test_message_is_accepted_and_busy_is_409(roots, turns):
    gate = []

    async def hold(fake):
        await gate[0].wait()
        return result()

    turns.append([hold])

    async def scenario(client):
        gate.append(asyncio.Event())
        cid = (await client.post("/api/claude/conversations", json={"project": "Robox"})).json()["id"]
        first = await client.post(f"/api/claude/conversations/{cid}/messages", json={"text": "היי"})
        second = await client.post(f"/api/claude/conversations/{cid}/messages", json={"text": "שוב"})
        gate[0].set()
        return first.status_code, second.status_code

    assert with_client(scenario) == (202, 409)


def test_unknown_conversation_is_404(roots, turns):
    assert call("POST", "/api/claude/conversations/nope/messages", {"text": "x"}).status_code == 404


def test_answer_unknown_request_is_404(roots, turns):
    cid = call("POST", "/api/claude/conversations", {"project": "Robox"}).json()["id"]
    res = call("POST", f"/api/claude/conversations/{cid}/answers", {"request_id": "nope", "allow": True})
    assert res.status_code == 404


def test_stream_replays_then_follows_without_duplicates():
    async def scenario():
        mgr = ConversationManager(client_factory=lambda opts: FakeClient(opts, [[delta("a"), result()]]))
        conv = await mgr.open("D:/p")
        conv.publish({"type": "you", "text": "earlier"})          # seq 1, already happened
        stream = claude_api.event_stream(conv, after=0, keepalive_s=0.05)
        first = await stream.__anext__()
        await conv.send("x")                                       # seq 2.. while listening
        chunks = [first] + [await stream.__anext__() for _ in range(3)]
        await stream.aclose()
        return chunks
    chunks = asyncio.run(scenario())
    seqs = [json.loads(c.split("data: ", 1)[1])["seq"] for c in chunks if c.startswith("id:")]
    assert seqs == sorted(set(seqs)) and seqs[0] == 1


def test_stream_sends_keepalives_when_quiet():
    async def scenario():
        mgr = ConversationManager(client_factory=lambda opts: FakeClient(opts, []))
        conv = await mgr.open("D:/p")
        stream = claude_api.event_stream(conv, after=0, keepalive_s=0.01)
        chunk = await stream.__anext__()
        await stream.aclose()
        return chunk
    assert asyncio.run(scenario()).startswith(": keep-alive")
