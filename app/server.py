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


@app.post("/api/premise/{premise_id}/override")
async def api_override(premise_id: str, value: str):
    """The analyst disagrees with an assumption and says so.

    This runs the identical code path an external market event uses — the same
    supersession, the same $graphLookup, the same change stream. A human is just
    another source a premise can die from, which is why no special casing is
    needed to support one.
    """
    old = await db.premises().find_one({"_id": premise_id})
    if not old:
        return {"error": "unknown premise"}

    # Preserve the premise's type; a numeric field must not silently become a string.
    new_value: object = value
    if isinstance(old.get("value"), (int, float)) and not isinstance(old.get("value"), bool):
        try:
            new_value = float(value)
            if float(value).is_integer() and isinstance(old["value"], int):
                new_value = int(float(value))
        except ValueError:
            return {"error": f"{old.get('field')} is numeric; '{value}' is not"}

    res = await graph.supersede_premise(
        premise_id, new_value,
        reason=f"Analyst override: {old.get('field')} {old.get('value')} → {new_value}",
        source_name="Analyst override — judgment, not a published source",
        klass="analyst_override",
    )

    sites = sorted({c["site_id"] for c in res["cascade"] if c.get("site_id")})
    await emit({
        "type": "cascade", "killed": premise_id, "field": old.get("field"),
        "old_value": old.get("value"), "new_value": new_value,
        "reason": f"You changed {old.get('field')}.",
        "staled": [{"id": c["_id"], "agent": c.get("agent"),
                    "site_id": c.get("site_id"), "field": c.get("field"),
                    "depth": c.get("depth", 0)} for c in res["cascade"]],
        "agents_crossed": sorted({c.get("agent") for c in res["cascade"] if c.get("agent")}),
    })
    if res["cascade"]:
        await emit({
            "type": "interrupt", "count": len(res["cascade"]), "sites": sites,
            "agents": sorted({c.get("agent") for c in res["cascade"] if c.get("agent")}),
            "headline": f"You changed {old.get('field')} from {old.get('value')} to {new_value}.",
            "by_analyst": True,
        })
        await asyncio.sleep(1.0)
        await engine.rerun_affected(2, sites or [s["_id"] for s in
                                    await db.sites().find({}).to_list(None)], emit=emit)

    return {"cascade": len(res["cascade"]), "sites": sites}


@app.get("/api/state")
async def api_state():
    sites = await db.sites().find({}).to_list(length=None)
    alloc = await db.allocations().find({}).sort("round", -1).to_list(length=1)
    # Superseded conclusions stay in the collection as history but never reach the
    # workbench — the analyst sees the current answer, or the fact that it's stale.
    concl = await db.conclusions().find(
        {"status": {"$ne": "superseded"}}).to_list(length=None)
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
async def api_graph(site: str | None = None, conclusion: str | None = None):
    """Nodes and edges for the cascade visualisation.

    Scoped to one site by default. The whole-portfolio graph is 258 nodes and
    1,340 edges — true, and unreadable. What an analyst needs is the chain behind
    the site they have open.
    """
    if conclusion:
        # The chain behind a single number: its premises, and for any premise that
        # is itself another agent's conclusion, that agent's premises too. This is
        # what an analyst actually needs to see — the whole-site graph is 500 edges.
        c = await db.conclusions().find_one({"_id": conclusion})
        if not c:
            return {"nodes": [], "edges": []}
        concl = [c]
        seen = set(c.get("depends_on", []))
        parents = await db.premises().find({"_id": {"$in": list(seen)}}).to_list(None)
        for p in parents:
            if p.get("trigger") == "derived" and p.get("derived_from"):
                pc = await db.conclusions().find_one({"_id": p["derived_from"]})
                if pc:
                    concl.append(pc)
                    seen |= set(pc.get("depends_on", []))
        prems = await db.premises().find({"_id": {"$in": list(seen)}}).to_list(None)
        nodes, edges = [], []
        for p in prems:
            nodes.append({"id": p["_id"], "kind": "premise", "label": p.get("field"),
                          "agent": p.get("owner_agent"), "status": p.get("status", "active"),
                          "klass": p.get("klass"), "trigger": p.get("trigger")})
        for cc in concl:
            nodes.append({"id": cc["_id"], "kind": "conclusion", "label": cc.get("field"),
                          "agent": cc.get("agent"), "status": cc.get("status", "active")})
            for d in cc.get("depends_on", []):
                if d in seen:
                    edges.append({"from": d, "to": cc["_id"]})
            if cc.get("publishes"):
                edges.append({"from": cc["_id"], "to": cc["publishes"], "derived": True})
        return {"nodes": nodes, "edges": edges, "focus": conclusion}

    concl_q = {"site_id": site, "status": {"$ne": "superseded"}} if site else {}
    concl = await db.conclusions().find(concl_q).to_list(length=None)

    if site:
        needed = {d for c in concl for d in c.get("depends_on", [])}
        needed |= {c["publishes"] for c in concl if c.get("publishes")}
        prems = await db.premises().find({"_id": {"$in": list(needed)}}).to_list(length=None)
    else:
        prems = await db.premises().find({}).to_list(length=None)
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
