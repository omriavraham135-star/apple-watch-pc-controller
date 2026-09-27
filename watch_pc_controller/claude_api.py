"""HTTP routes for talking to Claude Code from the watch."""

import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from watch_pc_controller.auth import client_is_local
from watch_pc_controller.claude_bridge import AuditLog
from watch_pc_controller.claude_projects import (
    BadProjectName,
    ProjectExists,
    UnknownProject,
    create_project,
    latest_session_id,
    latest_session_time,
    list_conversations,
    list_projects,
    project_roots,
    resolve_project,
)
from watch_pc_controller.claude_sessions import ConversationBusy, ConversationManager, ConversationStartFailed

router = APIRouter(prefix="/api/claude")

_audit = AuditLog(os.path.join(os.path.dirname(__file__), "claude_audit.jsonl"))
_manager = ConversationManager(audit=_audit.record)


def get_manager() -> ConversationManager:
    return _manager


class NewProject(BaseModel):
    name: str


class OpenConversation(BaseModel):
    project: str
    session_id: Optional[str] = None
    new: bool = False


class Message(BaseModel):
    text: str


def _conversation(cid: str):
    try:
        return get_manager().get(cid)
    except KeyError:
        raise HTTPException(status_code=404, detail="אין שיחה כזו")


def _resolve(name: str) -> str:
    try:
        return resolve_project(name, project_roots())
    except (UnknownProject, BadProjectName):
        raise HTTPException(status_code=404, detail="אין פרויקט כזה")


# ------------------------------------------------------------- projects

@router.get("/projects")
def projects():
    waiting = get_manager().waiting_projects()
    return {"projects": [
        {"name": p["name"], "last_activity": p["last_activity"], "waiting": p["path"] in waiting}
        for p in list_projects(project_roots(), last_activity=latest_session_time)
    ]}


@router.post("/projects", status_code=201)
def new_project(req: NewProject):
    try:
        path = create_project(req.name, project_roots())
    except ProjectExists:
        raise HTTPException(status_code=409, detail="כבר יש פרויקט בשם הזה")
    except BadProjectName:
        raise HTTPException(status_code=422, detail="שם פרויקט לא תקין")
    return {"name": os.path.basename(path)}


@router.get("/projects/{name}/conversations")
def conversations_of(name: str):
    return {"conversations": list_conversations(_resolve(name))}


# ------------------------------------------------------------- conversations

@router.post("/conversations")
async def open_conversation(req: OpenConversation):
    path = _resolve(req.project)
    session_id = None if req.new else (req.session_id or latest_session_id(path))
    try:
        conv = await get_manager().open(path, session_id)
    except ConversationStartFailed as exc:
        raise HTTPException(status_code=503, detail=f"Claude Code לא עלה: {exc}")
    return {"id": conv.id, "session_id": conv.session_id}


@router.get("/conversations")
def open_conversations():
    return {"conversations": get_manager().summary()}


@router.post("/conversations/{cid}/messages", status_code=202)
async def send_message(cid: str, req: Message):
    conv = _conversation(cid)
    try:
        await conv.send(req.text)
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="Claude עדיין עובד על ההודעה הקודמת")
    return {"status": "accepted"}


@router.post("/conversations/{cid}/answers")
async def answer(cid: str, request: Request):
    body = await request.json()
    request_id = body.pop("request_id", None)
    if not request_id or not _conversation(cid).bridge.answer(request_id, body):
        raise HTTPException(status_code=404, detail="הבקשה הזו כבר לא מחכה")
    return {"status": "answered"}


@router.post("/conversations/{cid}/interrupt")
async def interrupt(cid: str):
    await _conversation(cid).interrupt()
    return {"status": "interrupted"}


@router.delete("/conversations/{cid}")
async def close_conversation(cid: str):
    _conversation(cid)
    await get_manager().close(cid)
    return {"status": "closed"}


# ------------------------------------------------------------- the stream

def _sse(item: dict) -> str:
    return f"id: {item['seq']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"


async def event_stream(conv, after: int, keepalive_s: float = 15.0):
    """Replay what was missed, then follow live; never send a seq twice."""
    queue = conv.listen()
    last = after
    try:
        for item in conv.replay(after):
            last = item["seq"]
            yield _sse(item)
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=keepalive_s)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item["seq"] <= last:
                continue
            last = item["seq"]
            yield _sse(item)
    finally:
        conv.unlisten(queue)


@router.get("/conversations/{cid}/events")
async def events(cid: str, after: int = 0):
    conv = _conversation(cid)
    return StreamingResponse(event_stream(conv, after), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------- audit

@router.get("/audit")
def audit(request: Request):
    if not client_is_local(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail="אפשר לראות את היומן רק מהמחשב")
    return {"entries": _audit.recent(100)}
