"""The invalidation core.

One agent's conclusion is published back into the premise store as a premise of
trigger `derived`. That single move is what makes cross-discipline invalidation
work: an edge from Engineering to Permitting is the same kind of edge as an edge
from a CARB price print to Finance. There is no special-case code for the
multi-agent case, which is the claim the third agent exists to prove.

The walk itself is one $graphLookup:

    premises._id  --(depends_on)-->  conclusions  --(publishes)-->  premises._id  ...

$graphLookup follows that alternation transitively and hands back every
conclusion reachable from a dead fact, tagged with its depth in the cascade.
"""
from datetime import datetime, timezone

from . import db


def utcnow():
    return datetime.now(timezone.utc)


async def dependents_of(premise_id: str):
    """Every conclusion transitively resting on `premise_id`, with cascade depth.

    connectFromField/connectToField do the alternation: start at the premise id,
    match conclusions whose `depends_on` contains it, hop to what each of those
    conclusions `publishes`, and repeat until nothing new is reachable.
    """
    pipeline = [
        {"$match": {"_id": premise_id}},
        {
            "$graphLookup": {
                "from": "conclusions",
                "startWith": "$_id",
                "connectFromField": "publishes",
                "connectToField": "depends_on",
                "as": "cascade",
                "depthField": "depth",
            }
        },
        {"$project": {"cascade": 1}},
    ]
    docs = await db.premises().aggregate(pipeline).to_list(length=1)
    if not docs:
        return []
    cascade = [c for c in docs[0].get("cascade", []) if c.get("status") == "active"]
    cascade.sort(key=lambda c: (c.get("depth", 0), c.get("agent", "")))
    return cascade


async def supersede_premise(premise_id: str, new_value, reason: str,
                            source_name=None, source_url=None, klass=None):
    """Kill a premise, install its replacement, and stale everything downstream.

    Returns the cascade so the caller can wake the affected agents. This function
    does not decide what to do about the damage — it only reports it.
    """
    old = await db.premises().find_one({"_id": premise_id})
    if old is None:
        return {"premise": None, "cascade": []}

    cascade = await dependents_of(premise_id)

    new_id = f"{premise_id}@{int(utcnow().timestamp())}"
    replacement = dict(old)
    replacement.update({
        "_id": new_id,
        "value": new_value,
        "retrieved_at": utcnow(),
        "status": "active",
        "supersedes": premise_id,
        "revision_reason": reason,
    })
    if source_name:
        replacement["source_name"] = source_name
    if source_url:
        replacement["source_url"] = source_url
    if klass:
        replacement["klass"] = klass

    await db.premises().insert_one(replacement)
    await db.premises().update_one(
        {"_id": premise_id},
        {"$set": {"status": "superseded", "superseded_by": new_id,
                  "superseded_at": utcnow()}},
    )

    if cascade:
        await db.conclusions().update_many(
            {"_id": {"$in": [c["_id"] for c in cascade]}},
            {"$set": {"status": "stale", "staled_at": utcnow(),
                      "staled_by": premise_id, "stale_reason": reason}},
        )
        # A stale conclusion's published premise is stale too — that is how the
        # cascade keeps travelling past a discipline boundary.
        published = [c["publishes"] for c in cascade if c.get("publishes")]
        if published:
            await db.premises().update_many(
                {"_id": {"$in": published}},
                {"$set": {"status": "stale", "staled_at": utcnow()}},
            )

    # Explicit string _id: every document in this system is addressable by a
    # readable key, and nothing ever carries a BSON ObjectId across the wire.
    await db.revisions().insert_one({
        "_id": f"rev-{premise_id}-{int(utcnow().timestamp() * 1000)}",
        "at": utcnow(),
        "killed_premise": premise_id,
        "killed_field": old.get("field"),
        "old_value": old.get("value"),
        "new_value": new_value,
        "new_premise": new_id,
        "reason": reason,
        "staled_conclusions": [
            {"id": c["_id"], "agent": c.get("agent"), "site_id": c.get("site_id"),
             "field": c.get("field"), "depth": c.get("depth", 0)}
            for c in cascade
        ],
        "cascade_size": len(cascade),
        "max_depth": max([c.get("depth", 0) for c in cascade], default=-1),
        "agents_crossed": sorted({c.get("agent") for c in cascade if c.get("agent")}),
    })

    return {"premise": replacement, "old": old, "cascade": cascade}


async def publish_conclusion(*, agent, site_id, field, value, unit, reasoning,
                             depends_on, round_no, klass="derived",
                             confidence=0.7, extra=None):
    """Write a conclusion and publish it as a premise other agents can depend on.

    The returned premise id is what makes this conclusion available as an input
    elsewhere. Everything cross-agent in this system flows through here.
    """
    cid = f"concl-{agent}-{site_id}-{field}-r{round_no}"
    pid = f"prem-derived-{agent}-{site_id}-{field}"

    conclusion = {
        "_id": cid,
        "agent": agent,
        "site_id": site_id,
        "field": field,
        "value": value,
        "unit": unit,
        "reasoning": reasoning,
        "depends_on": list(depends_on),
        "publishes": pid,
        "status": "active",
        "round": round_no,
        "created_at": utcnow(),
        "confidence": confidence,
    }
    if extra:
        conclusion.update(extra)

    await db.conclusions().replace_one({"_id": cid}, conclusion, upsert=True)

    derived_premise = {
        "_id": pid,
        "site_id": site_id,
        "field": field,
        "value": value,
        "unit": unit,
        "klass": klass,
        "source_name": f"{agent.title()} agent conclusion",
        "source_url": None,
        "retrieved_at": utcnow(),
        "expires_at": None,
        "confidence": confidence,
        "owner_agent": agent,
        "trigger": "derived",
        "derived_from": cid,
        "status": "active",
    }
    await db.premises().replace_one({"_id": pid}, derived_premise, upsert=True)
    return cid, pid


async def provenance_chain(conclusion_id: str):
    """Everything behind one number: its premises, and what produced those.

    This is what a provenance chip opens. It is also the honest answer to "would
    an investment committee approve this" — they approve models with receipts.
    """
    c = await db.conclusions().find_one({"_id": conclusion_id})
    if not c:
        return None

    prems = await db.premises().find(
        {"_id": {"$in": c.get("depends_on", [])}}
    ).to_list(length=None)

    for p in prems:
        if p.get("trigger") == "derived" and p.get("derived_from"):
            parent = await db.conclusions().find_one({"_id": p["derived_from"]})
            if parent:
                p["produced_by"] = {
                    "agent": parent.get("agent"),
                    "reasoning": parent.get("reasoning"),
                    "conclusion_id": parent["_id"],
                }

    counts = {}
    for p in prems:
        counts[p.get("klass", "unknown")] = counts.get(p.get("klass", "unknown"), 0) + 1

    return {"conclusion": c, "premises": prems, "class_counts": counts}


async def stale_conclusions():
    return await db.conclusions().find({"status": "stale"}).to_list(length=None)


async def calibration_report():
    """Read self-knowledge off the revision ledger — never off a claim.

    The brief wanted the agent to say "I've been wrong about interconnection
    timing." We only let it say that if the revisions collection proves it.
    """
    pipeline = [
        {"$unwind": "$staled_conclusions"},
        {"$group": {
            "_id": "$staled_conclusions.field",
            "times_revised": {"$sum": 1},
            "reasons": {"$addToSet": "$reason"},
            "agents": {"$addToSet": "$staled_conclusions.agent"},
        }},
        {"$sort": {"times_revised": -1}},
        {"$limit": 6},
    ]
    by_field = await db.revisions().aggregate(pipeline).to_list(length=None)

    killers = await db.revisions().aggregate([
        {"$group": {"_id": "$killed_field", "kills": {"$sum": 1},
                    "total_damage": {"$sum": "$cascade_size"}}},
        {"$sort": {"total_damage": -1}},
        {"$limit": 5},
    ]).to_list(length=None)

    total = await db.revisions().count_documents({})
    return {"most_revised_fields": by_field, "most_destructive_premises": killers,
            "total_revisions": total}
