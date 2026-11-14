"""LaunchLocally controller API and web pages.

Run from the project root:  .venv/bin/python -m launchlocal.server   (port 8787)
Env: HOST (default 127.0.0.1), PORT (8787), PUBLIC_BASE_URL (base for the QR code).
"""
import asyncio
import json
import os
import re
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from launchlocal.common import PACKS, ROOT, RUNS, emit, load_env, read_json, write_json

WEB = ROOT / "web"
STATE_FILES = ("input", "brand", "facts", "script", "gate", "render")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

app = FastAPI(title="LaunchLocally")
RUNS.mkdir(exist_ok=True)


def rdir(run_id: str):
    # run ids come from URLs: reject anything that could leave runs/
    if not RUN_ID.match(run_id) or not (RUNS / run_id).is_dir():
        raise HTTPException(404, f"run not found: {run_id}")
    return RUNS / run_id


def is_end(line: bytes | str) -> bool:
    try:
        e = json.loads(line)
    except ValueError:
        return False
    # agents.py also emits system done/error per stage; only these end the run:
    # the final "run complete" (carries run_id) and a failed stage (coder failures are survivable)
    if e.get("agent") != "system":
        return False
    d = e.get("data") or {}
    if e.get("kind") == "done":
        return "run_id" in d
    return e.get("kind") == "error" and bool(d.get("fatal") or d.get("stage") not in (None, "coder"))


def event_lines(d) -> list[bytes]:
    p = d / "events.jsonl"
    return [l for l in p.read_bytes().split(b"\n") if l.strip()] if p.exists() else []


def run_status(d) -> str:
    lines = event_lines(d)
    for line in reversed(lines):
        if is_end(line):
            return json.loads(line)["kind"]
    if not lines:
        return "done" if (d / "render.json").exists() else "new"
    return "running" if time.time() - (d / "events.jsonl").stat().st_mtime < 600 else "stalled"


def maybe_json(path):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/run/{run_id}")
def run_page(run_id: str):
    rdir(run_id)
    return FileResponse(WEB / "run.html")


@app.get("/api/packs")
def packs():
    out = []
    for p in sorted(PACKS.glob("*.json")):
        pack = maybe_json(p) or {}
        out.append({"id": p.stem, "label": pack.get("label", p.stem), "direction": pack.get("direction", "")})
    return out


@app.get("/api/runs")
def runs():
    out = []
    for d in RUNS.iterdir():
        if not d.is_dir() or not RUN_ID.match(d.name) or d.name.startswith(("dev-", "fixture")):
            continue  # development and fixture runs stay off the launcher
        inp = maybe_json(d / "input.json")
        if inp is None and not (d / "events.jsonl").exists():
            continue
        inp = inp or {}
        out.append({
            "run_id": d.name,
            "url": inp.get("url", ""),
            "market": inp.get("market", ""),
            "product": (maybe_json(d / "brand.json") or {}).get("name", ""),
            "status": run_status(d),
            "has_video": (d / "video.mp4").exists(),
            "mtime": max((f.stat().st_mtime for f in d.iterdir()), default=d.stat().st_mtime),
        })
    return sorted(out, key=lambda r: -r["mtime"])


@app.get("/api/runs/{run_id}/state")
def state(run_id: str):
    d = rdir(run_id)
    out = {k: v for k in STATE_FILES if (v := maybe_json(d / f"{k}.json")) is not None}
    out["run_id"] = run_id
    out["status"] = run_status(d)
    out["has_video"] = (d / "video.mp4").exists()
    out["has_poster"] = (d / "poster.png").exists()
    out["public_base"] = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    market = (out.get("input") or {}).get("market", "")
    if RUN_ID.match(market or ""):
        pack = maybe_json(PACKS / f"{market}.json") or {}
        out["pack"] = {k: pack.get(k) for k in ("id", "label", "language", "language_name", "direction", "buyer_persona")}
    return out


def sse(line: bytes, n: int) -> str:
    return f"id: {n}\ndata: {line.decode('utf-8', 'replace')}\n\n"


END = "event: end\ndata: {}\n\n"


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request, replay: int = 0, speed: float = 1.0):
    d = rdir(run_id)
    path = d / "events.jsonl"

    async def replayed():
        prev = None
        for n, line in enumerate(event_lines(d), 1):
            try:
                ts = float(json.loads(line).get("ts") or 0)
            except ValueError:
                continue
            if prev is not None:
                # cap long silences so a replay never stalls on stage
                await asyncio.sleep(min(max(ts - prev, 0), 8) / max(speed, 0.1))
            prev = ts
            yield sse(line, n)
        yield END

    async def live():
        # EventSource reconnects with Last-Event-ID; skip what it already has
        skip = int(request.headers.get("last-event-id") or 0)
        n = pos = idle = 0
        buf = b""
        while not await request.is_disconnected():
            ended = False
            if path.exists():
                with open(path, "rb") as f:
                    f.seek(pos)
                    buf += f.read()
                    pos = f.tell()
                *lines, buf = buf.split(b"\n")
                for line in lines:
                    if not line.strip():
                        continue
                    n += 1
                    if n > skip:
                        yield sse(line, n)
                    ended = ended or is_end(line)
            if ended:
                yield END
                return
            idle += 1
            if idle % 25 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(
        replayed() if replay else live(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class LaunchBody(BaseModel):
    url: str
    market: str = "ja-JP"


def _run_pipeline(launch, url: str, market: str, run_id: str) -> None:
    d = RUNS / run_id
    try:
        # launch() returns at once; the pipeline keeps running and emits its own "run complete"
        asyncio.run(launch(url, market, run_id))
    except Exception as exc:  # the waiting screen must show the failure, not hang
        emit(d, "system", "error", f"Pipeline failed: {type(exc).__name__}: {exc}"[:400], fatal=True)


@app.post("/api/launch")
def launch_run(body: LaunchBody):
    url = body.url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    host = urlparse(url).hostname or ""
    if "." not in host:
        raise HTTPException(400, "Enter a product URL, for example https://www.daytona.io")
    if not RUN_ID.match(body.market) or not (PACKS / f"{body.market}.json").exists():
        raise HTTPException(400, f"Unknown market: {body.market}")
    try:
        from launchlocal.agents import launch
    except Exception as exc:
        raise HTTPException(503, f"Pipeline not available: cannot import launch from launchlocal.agents ({type(exc).__name__}: {exc})")
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower().removeprefix("www.")).strip("-")
    run_id = f"{slug}-{datetime.now():%Y%m%d-%H%M%S}"
    d = RUNS / run_id
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "input.json", {"run_id": run_id, "url": url, "market": body.market})
    # own thread and event loop: pipeline stages are blocking and must not stall the SSE streams
    threading.Thread(target=_run_pipeline, args=(launch, url, body.market, run_id), daemon=True).start()
    return {"run_id": run_id}


# video.mp4 (range requests), audio, assets, poster
app.mount("/runs", StaticFiles(directory=RUNS), name="runs")


if __name__ == "__main__":
    import uvicorn

    load_env()
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8787")))
