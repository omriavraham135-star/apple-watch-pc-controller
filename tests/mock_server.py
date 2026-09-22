#!/usr/bin/env python3
"""A stand-in for the PC, so the watch app can be seen with real content.

The real server needs pycaw and a Windows audio endpoint, so it cannot run on
the macOS machine that builds the app. This serves the same shapes over the
same paths with fixed, plausible values — enough for the simulator to render
every page populated rather than empty.

    python3 tests/mock_server.py --port 8000

Reads nothing, changes nothing, and answers every write with success.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATUS = {
    "status": "online",
    "volume": 62,
    "is_muted": False,
    "local_ip": "127.0.0.1",
}

POWER = {
    "actions": [
        {"action": "lock", "label": "נעילה", "destructive": False, "hold_seconds": 0.0},
        {"action": "sleep", "label": "שינה", "destructive": False, "hold_seconds": 0.0},
        {"action": "restart", "label": "הפעלה מחדש", "destructive": True, "hold_seconds": 2.0},
        {"action": "shutdown", "label": "כיבוי", "destructive": True, "hold_seconds": 3.0},
    ]
}

STATS = {
    "cpu": 37,
    "memory": 68,
    "disk": 83,
    "memory_used_gb": 10.8,
    "memory_total_gb": 15.9,
    "disk_free_gb": 40.1,
    "disk_total_gb": 237.4,
    "uptime_seconds": 17405,
}

ACTIONS = {
    "actions": [
        {"id": "screenshot", "label": "צילום מסך", "icon": "camera.viewfinder", "process": None},
        {"id": "minimize-all", "label": "מזעור הכל", "icon": "rectangle.3.group", "process": None},
        {"id": "chrome", "label": "Chrome", "icon": "globe", "process": "chrome.exe"},
        {"id": "explorer", "label": "סייר הקבצים", "icon": "folder", "process": "explorer.exe"},
        {"id": "taskmgr", "label": "מנהל המשימות", "icon": "chart.bar", "process": "Taskmgr.exe"},
        {"id": "settings", "label": "הגדרות", "icon": "gearshape", "process": "SystemSettings.exe"},
    ]
}

# Two apps open, so the live state is visible in a screenshot rather than
# something that has to be taken on trust.
ACTION_STATUS = {
    "statuses": {
        "screenshot": {"running": False, "pid": None},
        "minimize-all": {"running": False, "pid": None},
        "chrome": {"running": True, "pid": 4211},
        "explorer": {"running": True, "pid": 1180},
        "taskmgr": {"running": False, "pid": None},
        "settings": {"running": False, "pid": None},
    }
}

ROUTES = {
    "/api/status": STATUS,
    "/api/power": POWER,
    "/api/stats": STATS,
    "/api/actions": ACTIONS,
    "/api/actions/status": ACTION_STATUS,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        payload = ROUTES.get(self.path)
        if payload is None:
            self._send({"detail": "not found"}, 404)
        else:
            self._send(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {}

        if self.path == "/api/volume":
            STATUS["volume"] = max(0, min(100, int(body.get("volume", STATUS["volume"]))))
            self._send({"status": "success", "volume": STATUS["volume"]})
        elif self.path == "/api/command":
            self._send({
                "status": "success",
                "intent": "set_absolute",
                "feedback": "ווליום כוון ל-80%",
                "details": {"new_volume": 80, "is_muted": False},
            })
        elif self.path == "/api/power":
            self._send({"status": "success", "details": {"action": body.get("action")}})
        elif self.path.startswith("/api/actions/"):
            action_id = self.path.rsplit("/", 1)[-1]
            known = {a["id"] for a in ACTIONS["actions"]}
            if action_id not in known:
                self._send({"detail": "unknown action"}, 404)
                return
            running = ACTION_STATUS["statuses"][action_id]["running"]
            self._send({
                "status": "success",
                "details": {
                    "id": action_id,
                    "label": action_id,
                    "status": "focused" if running else "launched",
                },
            })
        else:
            self._send({"detail": "not found"}, 404)

    def log_message(self, fmt, *args):
        # The CI log is for build output; requests would drown it.
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock PC listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
