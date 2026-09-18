import os
import socket
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from watch_pc_controller.volume_controller import VolumeController
from watch_pc_controller.nlp_parser import parse_voice_command

app = FastAPI(title="Apple Watch PC Controller API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

volume_ctrl = VolumeController()

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
