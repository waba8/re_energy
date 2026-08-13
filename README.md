# PREMISE

**Every number knows why it's true — and when it stopped being true.**

Built at the MongoDB Persistent Context Sprint Hackathon, Pier 48 SF, 13 Aug 2026.
Everything in `app/` was written during the 1:30–5:00 PM build window.

---

## The problem

Every agent memory system stores **what happened**. Almost none store **why the
agent decided** — and none notice when the reason expires.

A real estate development team underwriting battery storage runs on hundreds of
facts that quietly rot: a utility republishes its hosting-capacity dataset, a
soil report comes back, a credit price prints, another discipline revises an
assumption you built on. An analyst cannot hold six sites × forty assumptions in
their head. Nothing tells them which of yesterday's conclusions just died.

## What this does

Three agents — **Engineering**, **Permitting**, **Finance** — underwrite six real
Bay Area parcels against a $40M budget.

Every number any agent produces records the **premises** it rests on: each with a
source, a URL, a retrieval date, a confidence, and an honesty class
(`measured` / `published` / `modeled` / `assumed`). When a premise dies, one
`$graphLookup` walks the dependency graph and invalidates every conclusion
resting on it — transitively, across discipline boundaries. A change stream wakes
the affected agents. The analyst is **interrupted mid-task**. Capital moves.

### The mechanism

One agent's conclusion is **published back into the premise store** as a premise
of trigger `derived`. That single move is the whole design: an edge from
Engineering to Permitting is the same kind of edge as an edge from a CARB price
print to Finance. Cross-agent invalidation needs no special-case code.

```
premises._id --(depends_on)--> conclusions --(publishes)--> premises._id --> ...
```

`$graphLookup` follows that alternation transitively. The third agent exists
partly to prove the claim: adding Permitting cost a prompt and a config entry,
not an architecture change.

### The conflict it makes visible

EPA sets risk-based cleanup standards by **intended reuse**. So when
contamination is confirmed at Cutting Blvd Yard:

- **Engineering** reads it as *good news* — industrial energy use tolerates that
  soil, and it's why the land is cheap.
- **Permitting** reads the same fact and objects — the community-benefit space
  committed to win the entitlement is a **reuse change**, which re-prices the
  same dirt from the industrial standard to the sensitive one.
- **Finance** watches basis jump and the deal break.

Observed in the run recorded for the demo: **17 conclusions staled across all
three agents, spread collapsed 173 bps → −184 bps, and $3.25M was pulled back
and redeployed.** One fact, three readings, one graph walk.

---

## MongoDB features, each load-bearing

| Feature | Role |
|---|---|
| **`$graphLookup`** | The transitive invalidation walk. Returns every dependent conclusion with its cascade depth. |
| **Change streams** | `revisions` is watched; an insert means a belief died, which wakes agents and pushes the interrupt to the browser over SSE. Nobody polls, nobody clicks. |
| **Aggregation pipelines** | Portfolio allocation, and the calibration report that reads self-knowledge off the revision ledger. |
| **Atlas Search** | Matches free-text real-world events to the premises they invalidate — real events don't arrive carrying our primary keys. Falls back to token overlap when the index isn't built. |

## Partner tools

- **OpenRouter** — all three agents' qualitative reasoning. 81 of 96 conclusions
  in the recorded run were live model calls; the rest fell back deterministically
  and are labelled `deterministic fallback` in the UI rather than hidden.
- **ElevenLabs** — voices the interrupt, with the browser's `speechSynthesis` as
  a keyless fallback so the interrupt always speaks.

## A deliberate split

**The LLM makes judgments. The ledger does arithmetic.** Language models are bad
calculators and good analysts, so the agents decide whether contamination is
gating, which entitlement path applies, and whether a deal clears — while basis,
yield, and spread are computed in Python where they're reproducible.

Relatedly: there are no magic numbers in the formulas. Round-trip efficiency,
cycle count, the 150bps hurdle, the equity ratio and a dozen others are all
**premises**, not constants — so they carry citations, admit when they have none,
and can be invalidated like anything else. Formula *structure* stays in code
(`spread = YoC − exit cap` is a definition, not a claim). Most of those
parameters are class `assumed` with no source, and the UI says so out loud.

---

## Running it

```bash
pip install motor pymongo fastapi "uvicorn[standard]" python-dotenv httpx
```

`.env` (gitignored — never committed):

```
DB_USERNAME=...
DB_PASSWORD=...
OPEN_ROUTER_API_KEY=...
ELEVENLABS_API_KEY=...        # optional; browser TTS is used without it
```

```bash
python -m uvicorn app.server:app --port 8000
```

Open <http://127.0.0.1:8000> → **reset** → **run baseline** → **contamination event**.

## Layout

```
app/db.py          connection and collection handles
app/seed_data.py   six real parcels; every premise with its source and honesty class
app/graph.py       the invalidation core — $graphLookup, supersession, provenance
app/agents.py      Engineering, Permitting, Finance
app/engine.py      seed, run a round, allocate capital, apply an event
app/server.py      FastAPI, SSE, the change-stream watcher
app/static/        the workspace (no build step)
```

## Honest limits

- Premises carry real published figures with real citations, but they were
  curated rather than scraped live. Live connectors to GeoTracker, EnviroStor,
  DataSF and the PG&E ICA portal are the obvious next step and were cut for time.
- Figures marked `assumed` have no source. That's the honest state of most
  numbers in a development model, and it's surfaced rather than hidden.
- The Atlas Search index isn't built in this sandbox, so event→premise matching
  runs on the token-overlap fallback.
- No auth, no tenancy, no migrations, no test suite. Single-user local demo.

## Where this goes

The invalidation ledger is the substrate a **governance layer** sits on: every
conclusion already records who decided, on what basis, and whether that basis
still holds. Add approval gates and an audit export and you have something an
investment committee can actually sign off on — which is the difference between a
model a real firm uses and one it doesn't.

Also deferred: full preconstruction PM (inspection milestones, permit-by-permit
tracking), capability routing so only the affected analysis re-runs instead of
the whole site, and interconnection queue-position tracking.
