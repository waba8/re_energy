"""Orchestration: seed, run a round, allocate capital, apply a real-world event."""
import asyncio

from . import agents, db, graph, seed_data


async def seed():
    """Load sites and premises. Idempotent — safe to re-run mid-demo."""
    for coll in (db.sites(), db.premises(), db.conclusions(), db.events(),
                 db.actions(), db.revisions(), db.allocations()):
        await coll.delete_many({})

    await db.sites().insert_many(seed_data.SITES)

    prems = seed_data.all_premises()
    for p in prems:
        p.setdefault("status", "active")
    await db.premises().insert_many(prems)
    await db.events().insert_many(seed_data.EVENTS)

    await db.premises().create_index("field")
    await db.premises().create_index("site_id")
    await db.premises().create_index("status")
    await db.conclusions().create_index("depends_on")
    await db.conclusions().create_index("publishes")
    await db.conclusions().create_index([("site_id", 1), ("agent", 1)])

    return {"sites": len(seed_data.SITES), "premises": len(prems),
            "events": len(seed_data.EVENTS)}


async def run_round(round_no: int, emit=None):
    """Run all three agents over all six sites, in dependency order.

    Engineering first because Permitting depends on its sizing, Permitting before
    Finance because schedule feeds IRR. The back-edge (Finance's capex ceiling
    constraining Engineering) closes on the following round, which is exactly how
    it works on a real deal — you don't get the ceiling until someone underwrites.
    """
    sites = await db.sites().find({}).to_list(length=None)

    for agent_name in ("engineering", "permitting", "finance"):
        if emit:
            await emit({"type": "agent_start", "agent": agent_name, "round": round_no})
        fn = agents.AGENTS[agent_name]
        await asyncio.gather(*(fn(s, round_no) for s in sites))
        if emit:
            await emit({"type": "agent_done", "agent": agent_name, "round": round_no})

    alloc = await allocate(round_no)
    if emit:
        await emit({"type": "round_complete", "round": round_no, "allocation": alloc})
    return alloc


async def allocate(round_no: int):
    """Rank by development spread, fund until the $40M runs out.

    Only active conclusions count. A stale verdict cannot hold capital — that is
    the point of the whole system, expressed in one query filter.
    """
    budget = seed_data.PORTFOLIO_BUDGET_USD
    sites = await db.sites().find({}).to_list(length=None)

    eq = await db.premises().find_one({"field": "equity_ratio", "status": "active"})
    equity_ratio = float(eq["value"]) if eq else 0.35

    rows = []
    for s in sites:
        c = await db.conclusions().find_one(
            {"site_id": s["_id"], "field": "development_spread_bps", "status": "active"})
        v = await db.conclusions().find_one(
            {"site_id": s["_id"], "field": "verdict", "status": "active"})
        b = await db.conclusions().find_one(
            {"site_id": s["_id"], "field": "basis", "status": "active"})
        if not (c and v and b):
            rows.append({"site_id": s["_id"], "name": s["name"], "spread": None,
                         "verdict": "stale", "basis": None, "allocated": 0,
                         "reasoning": "Underwriting is stale pending revision."})
            continue
        rows.append({
            "site_id": s["_id"], "name": s["name"],
            "spread": c["value"], "verdict": v["value"], "basis": b["value"],
            "reasoning": v.get("reasoning", ""), "allocated": 0,
        })

    fundable = sorted(
        [r for r in rows if r["verdict"] == "allocate" and r["spread"] is not None],
        key=lambda r: -r["spread"])

    remaining = budget
    for r in fundable:
        equity = round(r["basis"] * equity_ratio)
        if equity <= remaining:
            r["allocated"] = equity
            remaining -= equity

    snapshot = {
        "_id": f"alloc-r{round_no}",
        "round": round_no,
        "budget": budget,
        "deployed": budget - remaining,
        "undeployed": remaining,
        "rows": rows,
        "at": graph.utcnow(),
    }
    await db.allocations().replace_one({"_id": snapshot["_id"]}, snapshot, upsert=True)
    return snapshot


async def match_event_to_premises(event: dict, limit: int = 6):
    """Find which premises a free-text event invalidates.

    Real events do not arrive carrying our primary keys. A CARB press release
    does not say "this kills prem-lcfs-price". Atlas Search bridges unstructured
    input to the structured dependency graph; if the search index isn't built we
    fall back to field-token overlap so the demo still runs.
    """
    query = f"{event['headline']} {event.get('body','')} {event.get('affects_hint','')}"

    try:
        hits = await db.premises().aggregate([
            {"$search": {
                "index": "premise_text",
                "text": {"query": query,
                         "path": ["field", "source_name", "note", "unit"]},
            }},
            {"$match": {"status": "active"}},
            {"$limit": limit},
            {"$addFields": {"score": {"$meta": "searchScore"}, "matched_by": "atlas_search"}},
        ]).to_list(length=limit)
        if hits:
            return hits
    except Exception:
        pass

    hint = (event.get("affects_hint") or "").lower()
    tokens = {t for t in hint.replace("_", " ").split() if len(t) > 3}
    rows = await db.premises().find({"status": "active"}).to_list(length=None)
    scored = []
    for r in rows:
        hay = f"{r.get('field','')} {r.get('source_name','')} {r.get('note','')}".lower()
        score = sum(1 for t in tokens if t in hay)
        if score:
            scored.append({**r, "score": score, "matched_by": "token_fallback"})
    scored.sort(key=lambda r: -r["score"])
    return scored[:limit]


# The scripted consequence of each event: which premise dies and what replaces it.
EVENT_EFFECTS = {
    "evt-contamination": [
        ("prem-site-2-contam", "known",
         "GeoTracker case opened; soil borings confirm hydrocarbon and lead contamination.",
         "SWRCB GeoTracker — open LUST case", "https://geotracker.waterboards.ca.gov/", "published"),
    ],
    "evt-ica-republish": [
        ("prem-site-3-ica", 13.5,
         "PG&E republished ICA; feeder capacity revised down on new upstream queue commitments.",
         "PG&E Integration Capacity Analysis (republished)", None, "published"),
    ],
    "evt-lcfs-print": [
        ("prem-lcfs-price", 66.50,
         "CARB Q3 print: first quarterly deficit in over four years, deficits outpacing credits by ~1.7M tonnes.",
         "CARB LCFS Quarterly Data Summary, Q3", "https://ww2.arb.ca.gov/resources/documents/lcfs-quarterly-data-spreadsheet", "published"),
        ("prem-ra-price", 8.60,
         "Capacity pricing firms alongside the LCFS move; bilateral range re-marked upward.",
         "Re-marked from CPUC RA filings", None, "modeled"),
    ],
}


async def apply_event(event_id: str, emit=None):
    """The full loop: event lands → find what it kills → cascade → re-run → reallocate."""
    event = await db.events().find_one({"_id": event_id})
    if not event:
        return {"error": "unknown event"}

    if emit:
        await emit({"type": "event", "event": {k: event[k] for k in
                    ("_id", "headline", "body", "source_name", "source_url")}})

    matched = await match_event_to_premises(event)
    if emit:
        await emit({"type": "matched", "premises": [
            {"id": m["_id"], "field": m.get("field"), "score": m.get("score"),
             "matched_by": m.get("matched_by")} for m in matched]})

    all_cascade, affected_sites = [], set()
    for pid, new_val, reason, sname, surl, klass in EVENT_EFFECTS.get(event_id, []):
        res = await graph.supersede_premise(pid, new_val, reason, sname, surl, klass)
        for c in res["cascade"]:
            all_cascade.append(c)
            if c.get("site_id"):
                affected_sites.add(c["site_id"])
        if emit:
            await emit({
                "type": "cascade",
                "killed": pid,
                "field": res["old"].get("field") if res.get("old") else None,
                "old_value": res["old"].get("value") if res.get("old") else None,
                "new_value": new_val,
                "reason": reason,
                "staled": [{"id": c["_id"], "agent": c.get("agent"),
                            "site_id": c.get("site_id"), "field": c.get("field"),
                            "depth": c.get("depth", 0)} for c in res["cascade"]],
                "agents_crossed": sorted({c.get("agent") for c in res["cascade"] if c.get("agent")}),
            })

    if emit and all_cascade:
        await emit({
            "type": "interrupt",
            "count": len(all_cascade),
            "sites": sorted(affected_sites),
            "agents": sorted({c.get("agent") for c in all_cascade if c.get("agent")}),
            "headline": event["headline"],
        })

    return {"cascade": len(all_cascade), "sites": sorted(affected_sites)}


async def rerun_affected(round_no: int, site_ids, emit=None):
    """Re-derive only what went stale. Untouched sites keep their conclusions."""
    sites = await db.sites().find({"_id": {"$in": list(site_ids)}}).to_list(length=None)
    for agent_name in ("engineering", "permitting", "finance"):
        if emit:
            await emit({"type": "agent_start", "agent": agent_name, "round": round_no})
        fn = agents.AGENTS[agent_name]
        await asyncio.gather(*(fn(s, round_no) for s in sites))
        if emit:
            await emit({"type": "agent_done", "agent": agent_name, "round": round_no})
    alloc = await allocate(round_no)
    if emit:
        await emit({"type": "round_complete", "round": round_no, "allocation": alloc})
    return alloc
