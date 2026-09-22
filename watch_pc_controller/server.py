import os
import socket

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from watch_pc_controller.actions import ActionRegistry, UnknownActionError
from watch_pc_controller.nlp_parser import parse_voice_command
from watch_pc_controller.power_controller import PowerController, UnknownPowerActionError
from watch_pc_controller.system_stats import get_stats
from watch_pc_controller.volume_controller import VolumeController

app = FastAPI(title="Apple Watch PC Controller API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

volume_ctrl = VolumeController()
power_ctrl = PowerController()
action_registry = ActionRegistry()


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class VoiceCommandRequest(BaseModel):
    text: str


class DirectVolumeRequest(BaseModel):
    volume: int


class PowerRequest(BaseModel):
    action: str


# --------------------------------------------------------------------------
# Status and volume
# --------------------------------------------------------------------------

@app.get("/api/status")
def get_status():
    return {
        "status": "online",
        "volume": volume_ctrl.get_volume(),
        "is_muted": volume_ctrl.is_muted(),
        "local_ip": get_local_ip()
    }


@app.post("/api/volume")
def set_volume_direct(req: DirectVolumeRequest):
    """Directly sets volume (0-100) from the Apple Watch slider with zero latency."""
    res = volume_ctrl.set_volume(req.volume)
    return {
        "status": "success",
        "volume": res["new_volume"],
        "details": res
    }


@app.post("/api/command")
def process_command(req: VoiceCommandRequest):
    parsed = parse_voice_command(req.text)
    intent = parsed.get("intent")

    if intent == "change_relative":
        res = volume_ctrl.change_volume(parsed["delta"])
        return {
            "status": "success",
            "intent": intent,
            "feedback": parsed["feedback"],
            "details": res
        }
    elif intent == "set_absolute":
        res = volume_ctrl.set_volume(parsed["target"])
        return {
            "status": "success",
            "intent": intent,
            "feedback": parsed["feedback"],
            "details": res
        }
    elif intent == "mute":
        res = volume_ctrl.set_mute(parsed["value"])
        return {
            "status": "success",
            "intent": intent,
            "feedback": parsed["feedback"],
            "details": res
        }
    else:
        return {
            "status": "unknown_command",
            "intent": "unknown",
            "feedback": parsed["feedback"],
            "current_volume": volume_ctrl.get_volume()
        }


# --------------------------------------------------------------------------
# Power
# --------------------------------------------------------------------------

@app.get("/api/power")
def list_power_actions():
    """Which power buttons to draw, and which of them need press-and-hold."""
    return {"actions": power_ctrl.describe()}


@app.post("/api/power")
def run_power_action(req: PowerRequest):
    try:
        res = power_ctrl.execute(req.action)
    except UnknownPowerActionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "success", "details": res}


# --------------------------------------------------------------------------
# Machine vitals
# --------------------------------------------------------------------------

@app.get("/api/stats")
def read_stats():
    return get_stats()


# --------------------------------------------------------------------------
# User-defined actions
# --------------------------------------------------------------------------

@app.get("/api/actions")
def list_actions():
    return {"actions": action_registry.list_actions()}


@app.get("/api/actions/status")
def action_statuses():
    """Which action's app is open right now. Polled, so it stays cheap."""
    return {"statuses": action_registry.statuses()}


@app.post("/api/actions/reload")
def reload_actions():
    """Pick up edits to actions.json without restarting the server."""
    action_registry.reload()
    return {"status": "success", "actions": action_registry.list_actions()}


@app.post("/api/actions/{action_id}")
def run_action(action_id: str):
    try:
        res = action_registry.run(action_id)
    except UnknownActionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "success", "details": res}


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

def _serve_script(name: str) -> Response:
    """Serve a dashboard module by a fixed name — no path ever comes from a request."""
    path = os.path.join(os.path.dirname(__file__), name)
    with open(path, "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/javascript")


@app.get("/orb.js")
def orb_script():
    """The particle orb renderer."""
    return _serve_script("orb.js")


@app.get("/watch-ui.js")
def watch_ui_script():
    """The watch interface, instantiated once per watch on the page."""
    return _serve_script("watch-ui.js")


@app.get("/", response_class=HTMLResponse)
def test_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    current_ip = get_local_ip()
    vol = volume_ctrl.get_volume()
    muted = "true" if volume_ctrl.is_muted() else "false"

    html = html.replace("{{CURRENT_IP}}", current_ip)
    html = html.replace("{{VOL}}", str(vol))
    html = html.replace("{{MUTED}}", muted)

    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    local_ip = get_local_ip()
    print(f"[*] Starting Apple Watch PC Controller server on http://{local_ip}:8000 and http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
