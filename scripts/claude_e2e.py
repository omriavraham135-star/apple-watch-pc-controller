"""One real conversation with Claude Code through the running server's API.

Start the server first (py -m uvicorn watch_pc_controller.server:app --port 8000).
It works in a scratch project, allows exactly one harmless command and
declines anything else, answers Claude's question, and checks the result.
"""

import asyncio
import json
import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000") + "/api/claude"
PROJECT = "claude-watch-scratch"
SAFE = 'py -c "print(6*7)"'
STEPS = [
    "צור קובץ hello.txt שמכיל את המילה שלום.",
    f"הרץ את הפקודה הזו בדיוק: {SAFE} ואמור לי מה יצא.",
    "השתמש בכלי AskUserQuestion כדי לשאול אותי איזה צבע אני מעדיף, אדום או כחול. אחר כך אמור לי מה בחרתי.",
]


async def follow(client, cid, turn_done, log):
    async with client.stream("GET", f"{BASE}/conversations/{cid}/events", timeout=None) as res:
        async for line in res.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: "):])
            log.append(event)
            kind = event["type"]
            if kind == "approval":
                answer = {"request_id": event["id"], "allow": event["command"] == SAFE}
                await client.post(f"{BASE}/conversations/{cid}/answers", json=answer)
            elif kind == "question":
                question = event["questions"][0]
                labels = [o["label"] for o in question["options"]]
                pick = next((l for l in labels if "כחול" in l), labels[0] if labels else "כחול")
                answer = {"request_id": event["id"], "answers": {question["question"]: pick}}
                await client.post(f"{BASE}/conversations/{cid}/answers", json=answer)
            if kind != "text":
                print("  ", json.dumps(event, ensure_ascii=False)[:200])
            if kind in ("done", "error"):
                turn_done.set()


async def main() -> int:
    async with httpx.AsyncClient(timeout=60) as client:
        await client.post(f"{BASE}/projects", json={"name": PROJECT})          # 201, or 409 if it exists
        res = await client.post(f"{BASE}/conversations", json={"project": PROJECT, "new": True})
        res.raise_for_status()
        cid = res.json()["id"]
        turn_done, log = asyncio.Event(), []
        reader = asyncio.create_task(follow(client, cid, turn_done, log))
        for text in STEPS:
            turn_done.clear()
            print(">>>", text)
            (await client.post(f"{BASE}/conversations/{cid}/messages", json={"text": text})).raise_for_status()
            await asyncio.wait_for(turn_done.wait(), 240)
        reader.cancel()
        audit = (await client.get(f"{BASE}/audit")).json()["entries"]
        conversations = (await client.get(f"{BASE}/projects/{PROJECT}/conversations")).json()["conversations"]
        await client.delete(f"{BASE}/conversations/{cid}")

    kinds = [e["type"] for e in log]
    seqs = [e["seq"] for e in log]
    checks = {
        "the file was written without asking": any(e["type"] == "tool" and e["name"] == "Write" for e in log),
        "the command asked for approval": "approval" in kinds,
        "the question reached us": "question" in kinds,
        "three turns finished": kinds.count("done") == 3,
        "no errors": "error" not in kinds,
        "events in order, none twice": seqs == sorted(set(seqs)),
        "the decision is in the audit log": any(e.get("command") == SAFE for e in audit),
        "the conversation is listed": bool(conversations),
    }
    for name, ok in checks.items():
        print("OK  " if ok else "FAIL", name)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
