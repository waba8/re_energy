"""FastAPI app: SSE push, the change-stream watcher, and the workspace endpoints.

The change stream is the part that matters. Nobody polls, nobody clicks. An agent
writes a revision, MongoDB pushes it to the watcher, the watcher pushes it to the
browser, and the analyst gets interrupted mid-task. A dashboard is pulled from;
this pushes.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from . import db, engine, graph

STATIC = Path(__file__).parent / "static"

subscribers: list[asyncio.Queue] = []


async def emit(payload: dict):
    """Fan out one event to every connected browser."""
    dead = []
    for q in subscribers:
        try:
            q.put_nowait(payload)
        except Exception:
            dead.append(q)
    for q in dead:
        if q in subscribers:
            subscribers.remove(q)


async def watch_revisions():
    """Change stream on `revisions`. This is the unprompted wake-up.

    Watching `revisions` rather than `conclusions` is deliberate: a revision is
    by definition the moment a belief died, so every event on this stream is
    worth interrupting a human for. Watching conclusions would fire on routine
    writes and train the analyst to ignore it.
    """
    while True:
        try:
            async with db.revisions().watch(
                    [{"$match": {"operationType": "insert"}}]) as stream:
                async for change in stream:
                    doc = change["fullDocument"]
                    await emit({
                        "type": "change_stream",
                        "killed_field": doc.get("killed_field"),
                        "reason": doc.get("reason"),
                        "cascade_size": doc.get("cascade_size", 0),
                        "max_depth": doc.get("max_depth", 0),
                        "agents_crossed": doc.get("agents_crossed", []),
                    })
        except Exception as e:
            await emit({"type": "watcher_error", "detail": str(e)[:200]})
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(watch_revisions())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/stream")
async def stream():
    q: asyncio.Queue = asyncio.Queue()
    subscribers.append(q)

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(item, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if q in subscribers:
                subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/seed")
async def api_seed():
    res = await engine.seed()
    await emit({"type": "seeded", **res})
    return res


@app.post("/api/round/{n}")
async def api_round(n: int):
    return await engine.run_round(n, emit=emit)


@app.post("/api/event/{event_id}")
async def api_event(event_id: str):
    res = await engine.apply_event(event_id, emit=emit)
    if res.get("sites"):
        await asyncio.sleep(1.2)  # let the interrupt land before the repair starts
        await engine.rerun_affected(2, res["sites"], emit=emit)
    return res


@app.get("/api/state")
async def api_state():
    sites = await db.sites().find({}).to_list(length=None)
    alloc = await db.allocations().find({}).sort("round", -1).to_list(length=1)
    concl = await db.conclusions().find({}).to_list(length=None)
    acts = await db.actions().find({"status": "pending"}).to_list(length=None)

    by_site = {}
    for c in concl:
        by_site.setdefault(c["site_id"], []).append({
            "id": c["_id"], "agent": c["agent"], "field": c["field"],
            "value": c["value"], "unit": c.get("unit"), "status": c["status"],
            "reasoning": c.get("reasoning"), "depends_on": c.get("depends_on", []),
            "llm": c.get("llm", False),
        })

    return {
        "sites": sites,
        "allocation": alloc[0] if alloc else None,
        "conclusions": by_site,
        "actions": acts,
        "stale_count": sum(1 for c in concl if c["status"] == "stale"),
    }


@app.get("/api/provenance/{conclusion_id}")
async def api_provenance(conclusion_id: str):
    """Every number's receipt: what it rests on, and who produced those."""
    res = await graph.provenance_chain(conclusion_id)
    return res or {"error": "not found"}


@app.get("/api/calibration")
async def api_calibration():
    return await graph.calibration_report()


@app.get("/api/graph")
async def api_graph():
    """Nodes and edges for the cascade visualisation."""
    prems = await db.premises().find({}).to_list(length=None)
    concl = await db.conclusions().find({}).to_list(length=None)
    nodes, edges = [], []
    for p in prems:
        nodes.append({"id": p["_id"], "kind": "premise", "label": p.get("field"),
                      "agent": p.get("owner_agent"), "site": p.get("site_id"),
                      "status": p.get("status", "active"), "klass": p.get("klass"),
                      "trigger": p.get("trigger")})
    for c in concl:
        nodes.append({"id": c["_id"], "kind": "conclusion", "label": c.get("field"),
                      "agent": c.get("agent"), "site": c.get("site_id"),
                      "status": c.get("status", "active")})
        for d in c.get("depends_on", []):
            edges.append({"from": d, "to": c["_id"]})
        if c.get("publishes"):
            edges.append({"from": c["_id"], "to": c["publishes"], "derived": True})
    return {"nodes": nodes, "edges": edges}


@app.post("/api/action/{action_id}/approve")
async def api_approve(action_id: str):
    """The human decides. The agent only ever recommends."""
    await db.actions().update_one({"_id": action_id},
                                  {"$set": {"status": "approved",
                                            "approved_at": graph.utcnow()}})
    await emit({"type": "action_approved", "id": action_id})
    return {"ok": True}


@app.get("/api/voice")
async def api_voice(text: str):
    """ElevenLabs TTS if a key is present; the browser falls back to speechSynthesis."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        return {"available": False}
    import httpx
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": key},
            json={"text": text, "model_id": "eleven_turbo_v2_5"},
        )
        if r.status_code != 200:
            return {"available": False, "detail": r.text[:200]}
    from fastapi.responses import Response
    return Response(content=r.content, media_type="audio/mpeg")
