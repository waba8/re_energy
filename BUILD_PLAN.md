# PREMISE — Build Plan

**Every number knows why it's true — and when it stopped being true.**

MongoDB Persistent Context Sprint · Aug 13, 2026 · Build window 2:40–4:35 PM · Submit by 5:00 PM

Supersedes the execution sections of `PROJECT_BRIEF.md`. The brief remains the record of the original thinking; §2.5 and §7 of it are explicitly overridden here.

---

## 1. What it is, in one paragraph

Three agents — **Engineering**, **Permitting**, **Finance** — underwrite six Bay Area battery-storage sites against a $40M budget. Every number any agent produces carries its **premises**: the specific facts it rests on, each with a source, a URL, a retrieval date, and an honesty class (`measured | published | modeled | assumed`). When a premise dies — a market print lands, a dataset is republished, another agent revises a finding — a single `$graphLookup` walks the dependency graph and invalidates every conclusion resting on it, transitively, across discipline boundaries. A change stream wakes the affected agents. The analyst is **interrupted mid-task**, by voice. Capital reallocates. And where the revision requires a human — a call to a planning department, a meeting before a deadline — the system drafts the action and asks for approval.

**The mechanism:** one agent's conclusion is published as another agent's premise, of class `derived`. Cross-discipline invalidation is therefore the same graph edge as any other. No special-case code. Adding the third agent proves it.

---

## 2. What we cut from the brief, and why

| Cut | Reason |
|---|---|
| Live scraping (GeoTracker, DataSF, PG&E ICA) | 30–45 min each. Curated real figures with real citations are indistinguishable on video and strictly more validated. Pull live only if ahead at 4:00. |
| §2.5 as "a constraint inside the RE agent" | Produces no visible state change. The *insight* survives — relocated into the Permitting agent, where it produces behavior. |
| Terminal/log aesthetic | Round 1 is a video; Round 2 is an audience vote. Audiences vote for what they can see. The cascade animation is promoted from stretch goal to core. |
| Round-3 calibration read from claimed history | Rules forbid claiming history we didn't build. Instead: run all three rounds live so the system accumulates its own `revisions` history during the demo, then read calibration off the collection. True and provable. |
| Vector search use #3 (capability routing) | Stretch only. Uses #1 and #2 ship. |
| Six sites fully modeled | Six sites exist; three carry deep premise chains. The cascade only needs depth where it fires. |

---

## 3. The three agents and the cycle

**Engineering** → `max_mw`, `max_mwh`, `duration_hours`, `capex_per_kwh`, `buildable_area_sqft`, `service_upgrade_required`

**Permitting & Preconstruction** → `months_to_entitle`, `entitlement_path` (by-right | CUP | CEQA), `hma_required` (NFPA 855 2026), `cleanup_standard_triggered`, `human_actions[]`

**Finance / RE** → `basis`, `yield_on_cost`, `development_spread`, `irr`, `verdict`, `allocation_usd`, and back-constraints `capex_ceiling`, `required_yield`

The cycle, which is the point:

```
Engineering sizes the battery
  → setbacks + footprint become Permitting's premise
    → Permitting emits schedule + entitlement path
      → schedule becomes Finance's premise (IRR, ITC deadline)
        → Finance emits capex ceiling
          → constrains Engineering
```

**The signature demo beat (this is §2.5, made visible):** contamination is confirmed at Site 2. Engineering reads it as *good news* — tolerable for an industrial energy use, and it's why the land is cheap. Permitting reads the same fact and objects: the community-benefit space committed to for the entitlement path is a **reuse change**, and EPA cleanup standards are set by intended reuse — higher standard, added months. Finance's IRR breaks on the schedule. Capital moves. Same fact, opposite sign, three agents, one graph walk.

---

## 4. Data model

```
sites        6 real Bay Area parcels — name, address, apn, lot_sqft, zoning, utility

premises     value, unit, class: measured|published|modeled|assumed,
             source_name, source_url, retrieved_at, expires_at, confidence,
             owner_agent, status: active|superseded, superseded_by,
             trigger: watched|expiring|derived, embedding

conclusions  agent, site_id, field, value, reasoning, depends_on: [premise_id],
             status: active|stale|superseded, round, embedding
             (published back into `premises` as class `derived`)

events       incoming real-world facts, raw text + timestamp + embedding

actions      human_action_required — draft outreach, deadline, approval state

revisions    append-only: what died, what it killed, what replaced it, when

allocations  portfolio snapshot per round — who got capital and why
```

**Provenance is non-negotiable and on-screen.** Every number in the UI is a chip. Click it: value, unit, source name, live URL, retrieved-at, honesty class, and the reasoning chain that consumed it. An agent that knows which inputs are measured versus assumed is strictly more sophisticated than one that doesn't — and we say so out loud rather than hiding it.

---

## 5. MongoDB features, each load-bearing

- **`$graphLookup`** — transitive invalidation walk from a dead premise to every dependent conclusion, across agents.
- **Change streams** — an agent writes a revision → dependent agents wake unprompted → SSE pushes the interrupt to the browser. Nobody clicks anything.
- **Vector search (Atlas)** — (1) *dependency discovery*: real events don't arrive with our primary keys; embed the incoming event, search the premise store, find what it invalidates. (2) *precedent retrieval*: "have I revised a decision for this reason before?"
- **Aggregation pipeline** — portfolio allocation and the calibration read-off.

---

## 6. Stack

Python 3.13 · FastAPI · Motor (async Mongo) · SSE to a single self-contained HTML page · Tailwind via CDN · hand-rolled SVG dependency graph. **No build step.** OpenRouter for agent reasoning (partner credit). ElevenLabs for the voiced interrupt.

---

## 7. Timeline

| Time | Work | Owner |
|---|---|---|
| 2:40–2:55 | Atlas: DB user, network access, connection string. Seed collections. | **Will + Claude, together** |
| 2:40–3:10 | Schema, seed data with real citations, premise/conclusion write path | Claude |
| 3:10–3:35 | `$graphLookup` invalidation + change stream → SSE interrupt | Claude |
| 3:35–4:00 | Three agents via OpenRouter; vector index + dependency discovery | Claude |
| 4:00–4:20 | Workspace UI: allocation, provenance chips, cascade graph, action queue | Claude |
| 4:20–4:30 | ElevenLabs voiced interrupt | Claude |
| 4:30–4:40 | Full rehearsal of all three rounds end to end | Both |
| 4:40–5:00 | Record 60s video, push public repo, submit | Both |

**Never cut:** the interrupt. Everything else is negotiable.

---

## 8. The 60-second video

| Sec | Frame |
|---|---|
| 0–8 | "Every agent memory system stores what happened. None store *why* — and none notice when the reason expires." |
| 8–20 | Six sites, $40M allocated. Click a number → its receipt: source, URL, retrieved-at, honesty class. |
| 20–32 | Analyst moves to Site 4. Contamination confirmed at Site 2. **The interrupt fires, out loud, unbidden.** |
| 32–46 | Graph lights up red. Engineering says cheap land; Permitting says reuse-change, higher cleanup standard, +9 months. Allocation re-sorts. |
| 46–56 | Action queue: "Pre-app meeting with Richmond Planning before the safe-harbor date. Draft ready. Approve?" |
| 56–60 | "One agent's conclusion is the other's premise. `$graphLookup` and change streams do the rest." |

No preamble. No team intro. No architecture slide.

---

## 9. Deliberately not built today

Recorded so we can resume. This project does not die at 5:00 PM.

- **Governance layer** — approval gates, roles, audit export. The invalidation ledger built today *is* the substrate this sits on: every conclusion already records who decided, on what basis, and whether that basis still holds.
- Live connectors to GeoTracker, EnviroStor, DataSF, PG&E ICA.
- Full preconstruction PM: inspection milestones, permit-by-permit tracking, contractor scheduling.
- Capability routing via vector search (selective re-analysis instead of full re-run).
- Real interconnection queue position tracking.
- Multi-user, multi-portfolio, real auth.

---

## 10. Verify before it goes on screen

Anything stated as fact in the demo needs a real source in the `source_url` field. Confirm before recording: NFPA 855 2026 HMA threshold · LCFS Q3 print and spot price · PG&E Rule 29 service limits · current ITC rules for standalone storage · RA duration requirement · EPA reuse-based cleanup standard. Anything unverified ships as class `modeled` or `assumed` and is labeled as such in the UI. That labeling is a feature, not an apology.
