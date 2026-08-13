# No Cold Start — An Analyst Workbench with Cross-Agent Belief Revision

**MongoDB Persistent Context Sprint · Aug 13, 2026 · Pier 48 SF**
Build window: 1:30 PM – 5:00 PM. Submission (repo + 60s video) due 5:00 PM.

---

## 1. The pitch

Every agent memory system stores **what happened**. Almost none store **why the agent decided** — and none notice when the reason expires.

We build a **workbench for a real estate analyst** underwriting battery storage sites. The analyst submits a batch of properties and works through them. Behind the workbench, an engineering agent continuously assesses what each site can physically support.

Every conclusion either party reaches carries its supporting premises. When a premise dies — a market print, a republished utility dataset, an engineering finding — every conclusion resting on it is invalidated, and **the workbench interrupts the analyst mid-task**: *"Engineering revised Site 2. Three of your conclusions are stale. Your allocation is wrong."*

The two agents are not peers passing messages. **One agent's conclusion is the other agent's premise.** That's what makes invalidation cascade across the discipline boundary through a single graph walk, with no special-case code.

**The product claim:** an analyst cannot hold six sites × forty assumptions in their head. The system catches what they'd miss.

**Closing line:** *"Real estate development is a pile of decisions with expiring premises. So is every agent in this room."*

### Why this fits the prompt
*"Every agent starts from nothing. Build one that doesn't."* An analyst closes the laptop and returns to a workbench that remembers every assumption, its source, and its shelf life. And: *"What you store, retrieve, and checkpoint should change what the system does next."* A fixed budget reallocated by stored reasoning is the most literal possible reading of that.

### Coverage of MongoDB's own multi-agent example

| Their pattern | Us |
|---|---|
| Shares context through MongoDB | Premises/conclusions in shared collections; cross-agent derivation |
| Coordinates through change streams so handoffs carry state | Yes — the handoff carries a dependency graph, not just state |
| Discovers capabilities via vector search | Reframed: we **discover dependencies** via vector search (see §5) |

### Prior art check
Truth maintenance systems (Doyle, 1979) — dependency-directed backtracking, justification-based belief revision — are well understood in classical AI and have essentially not been ported to LLM agent memory. The current wave stores conclusions and re-embeds them. We store justifications and invalidate them.

---

## 2. The domain — what these people actually do

### 2.1 The deal

A real estate development firm has **$40M to deploy** into battery energy storage sites in the Bay Area, with co-located EV charging where it pencils. Six candidate sites. An outside engineering team assesses what each site can physically support.

Two things make this real rather than a toy:
- The RE firm **cannot underwrite anything** until engineering gives them MW and MWh.
- Engineering **cannot finalize a configuration** until finance gives them a capex ceiling and required yield.

The dependency runs both directions. That's the whole product.

---

### 2.2 Real Estate / Finance Agent — the analyst's copilot

**Its job:** decide what each site is worth, what to pay, and where the $40M goes.

| Term | Meaning |
|---|---|
| **Basis** | All-in cost: land + hard costs + soft costs + interconnection |
| **Yield on Cost (YoC)** | Stabilized NOI ÷ total basis. The core development metric. |
| **Development spread** | YoC minus exit cap rate. Under ~150bps, most firms pass. |
| **IRR / equity multiple** | Time-weighted return. Schedule delays hit this directly. |
| **DSCR** | Debt service coverage ratio. Lender constraint on leverage. |
| **Ground lease vs. fee** | Buy the land, or buy and lease to an operator. Different risk, different basis. |
| **ITC** | Federal Investment Tax Credit. Standalone storage qualifies post-IRA. Adders for energy community / domestic content. *Verify current rules.* |
| **MACRS** | Accelerated depreciation. Material to after-tax returns. |
| **Entitlement risk** | Will the jurisdiction approve this use? CEQA exposure in CA. |

**Revenue lines it models:**
- **Resource Adequacy (RA) capacity payments** — CA pays for dispatchable capacity. Generally requires 4-hour duration. *Verify.*
- **Energy arbitrage** — charge cheap, discharge expensive.
- **Demand charge / subscription management** — under PG&E's BEV schedule, sites subscribe to kW blocks and pay overage penalties; a battery holding the site under its tier has direct, quantifiable value.
- **LCFS credits** — if EV charging is co-located. Scales with kWh dispensed.
- **Fuel margin** — retail charging spread.

**Output per site:** max supportable basis · pro forma revenue given engineering's configuration · YoC, IRR, spread · verdict (allocate $X / pass) **with the specific reason** · portfolio ranking and allocation of the $40M.

---

### 2.3 Engineering Agent — running in the background

**Its job:** determine what each site can physically support, what it costs, how long it takes.

| Term | Meaning |
|---|---|
| **Hosting capacity / ICA** | How much DER a feeder can absorb. PG&E publishes an Integration Capacity Analysis map, updated periodically. |
| **Rule 21** | CA's DER interconnection tariff. *Verify specifics.* |
| **Rule 29** | Service extensions for EV. PG&E limits a site to two 480V services; SCE to three. Caps expandability. |
| **POI** | Point of interconnection. |
| **MW vs MWh** | Power vs energy. 10MW/40MWh = "4-hour duration." **Duration determines which revenue markets you can sell into at all.** |
| **PCS / inverter** | Power conversion. Sizing sets the MW. |
| **AC vs DC coupling** | How storage ties to co-located generation or charging. |
| **Round-trip efficiency** | ~85–90%. Losses hit revenue. |
| **Degradation / augmentation** | Capacity fade; whether you design space to add cells later. |
| **NFPA 855** | Storage fire code. **2026 edition makes Hazard Mitigation Analysis mandatory above 1 kWh.** Setbacks scale with capacity. |
| **Buildable area** | Lot area minus setbacks, easements, fire access. The binding constraint on MWh. |
| **EPC cost** | Engineering/procurement/construction, quoted $/kWh installed. |
| **Long-lead equipment** | Transformers and switchgear drive the schedule. |

**Output per site:** max MW · max MWh · configuration (duration, charging co-location, battery-buffered or direct) · capex · months to energization · flags (contamination, setback conflicts, upgrade triggers).

---

### 2.4 The dependency map — memorize this

**Engineering → Finance**

| Engineering output | Determines downstream |
|---|---|
| `max_mw` | Revenue capacity ceiling |
| `duration_hours` | Whether RA capacity revenue qualifies **at all** |
| `capex_per_kwh` | Basis, therefore YoC |
| `months_to_energization` | IRR (time value) and ITC deadline eligibility |
| `setback_area_consumed` | Land left for community use → the entitlement path |
| `service_upgrade_required` | Capex **and** schedule simultaneously |

**Finance → Engineering** (don't skip this direction)

| Finance output | Constrains |
|---|---|
| `capex_ceiling` | Maximum configuration size |
| `required_yield` | Minimum revenue → minimum MW/duration |
| `hold_period` | Whether to design for augmentation |
| `lcfs_assumption` | Whether charging co-location justifies its complexity |

**Watched external premises** (stochastic — monitored)
LCFS credit price · RA capacity price · ITC rules and adders · PG&E BEV tariff · republished ICA hosting capacity · construction cost index · cost of capital

**Expiring external premises** (deterministic — scheduled)
ITC safe-harbor deadlines · interconnection queue position · LOI/PSA expiry · SGIP windows · Phase I ESA shelf life

---

### 2.5 The structural insight — why the agents genuinely conflict

EPA's brownfield guidance sets cleanup standards by **intended reuse**: housing on an old factory site requires far more remediation than a solar field on the same soil. Same report, opposite implication.

| Fact | Energy reads it as | Community/entitlement reads it as |
|---|---|---|
| Soil contamination | Tolerable — and *why the land is cheap* | Gating, expensive, sometimes fatal |
| Adjacent substation | Excellent — interconnection is everything | Poor public realm |
| Industrial zoning | Permitted by right | Assembly use may be prohibited |
| Large impervious lot | Ideal siting | Hostile ground plane |
| Inverter noise | Irrelevant | Nuisance complaints |

**Sites that score highest for one systematically score lowest for the other.** The dual-use thesis isn't a free lunch — it's a narrow band where the sign flips.

Implementation: a **constraint inside the RE agent**, not a third agent. When engineering upsizes the battery, setbacks eat the public-realm commitment carrying the entitlement path.

---

## 3. The workbench — interaction design

**Not a dashboard. Not two chat panes.** A tool an analyst operates, in the same spirit as MongoDB's own "coding agent" example.

**Panes:**
1. **Batch / site list** — submitted properties, current allocation, current verdict
2. **Working underwrite** — the site the analyst has open right now
3. **Revision inbox** — *first-class surface.* The queue of your own conclusions that have gone stale. Best single screenshot in the video.
4. **Engineering status strip** — ambient, thin, non-focal: *"Engineering: reassessing Site 3 — ICA republished..."*

**On the status strip:** hiding engineering from the *analyst's attention* is realistic. Hiding it from the *judge's attention* forfeits credit for the multi-agent architecture. Ambient, not invisible — a CI indicator, not a panel.

**The non-negotiable:** the cascade **interrupts** the analyst mid-task. Nobody requests the update. A dashboard is pulled from; this pushes. That's both the differentiator and the anti-dashboard defense.

**Aesthetic:** terminal/log over polished UI. Reads as infrastructure, builds fast, and ugly-but-autonomous beats pretty-but-manual.

---

## 4. Data model

```
sites          6 real Bay Area parcels
premises       { value, unit, source, source_url, class, confidence,
                 owner_agent, observed_at, expires_at, superseded_by, embedding }
conclusions    { agent, site_id, verdict, reasoning, depends_on: [premise_id],
                 status: active|stale|superseded, superseded_by, round, embedding }
events         incoming real-world facts, timestamped
allocations    portfolio snapshot per round — who got capital and why
```

**Premise classes** — each gets a different invalidation trigger:
- `watched` → change stream on external feed
- `expiring` → scheduled sweep on `expires_at`
- `derived` → **cascade**; this premise *is* another agent's conclusion

The `derived` class is the entire multi-agent mechanism. No special-case code.

---

## 5. MongoDB features — each load-bearing

**Change streams** — engineering writes a conclusion → RE agent wakes unprompted → analyst is interrupted. One of MongoDB's own suggested patterns in the guide.

**`$graphLookup`** — walk premise → dependent conclusions → their dependents, transitively, when a fact dies.

**Vector search — three uses, none decorative:**

1. **Dependency discovery (primary).** Real events don't arrive with your primary keys. *"CARB publishes Q3 LCFS data"* doesn't tell you which of 200 premises it invalidates. Embed the event, vector-search the premise store, surface semantically related premises, cascade from there. This is the bridge between messy real-world input and a structured dependency graph.
2. **Precedent retrieval.** When a conclusion goes stale, search past reasoning: *"have I revised a decision for this reason before?"* Powers the Round 3 calibration beat.
3. **Capability routing (stretch, ~20 min).** Engineering has named routines — interconnection, setback/fire-code, contamination, cost. When a premise dies, vector-search which routine applies instead of re-running all four. Selective re-analysis is a real efficiency, so it earns its place.

---

## 6. The three rounds

**Round 1 — Baseline.** Analyst submits the batch. Both agents cold-start on six sites. Engineering publishes configurations; RE underwrites against them; $40M allocated across the top N. Ledger fills live in ~20 seconds. *We claim no history we didn't just build.*

**Round 2 — Internal finding.** Engineering discovers real contamination via GeoTracker at one site and republished ICA hosting capacity at another. **Analyst is mid-underwrite on a different site when the interrupt fires.** Cascade → configurations change → underwriting goes stale → capital reallocates.

**Round 3 — External market event.** Q3 2025 LCFS print: first deficit in over four years, deficits outpacing credits by 1.7M tonnes, spot to $66.50. Cascade across all six. Then calibration: *"I've assumed 18-month interconnection on three sites and been wrong on two. Adjusting my prior — and it's the assumption doing the most work in my last five passes."*

Arc: **internal finding → external market → self-knowledge.**

---

## 7. Build timeline

| Time | Work | Cut if behind |
|---|---|---|
| 1:00–1:30 | Registration, **recruit a frontend person** | — |
| 1:30–2:00 | Atlas cluster, collections, seed load | — |
| 2:00–2:45 | Premise/conclusion write path + `$graphLookup` invalidation | — |
| 2:45–3:15 | Change stream watcher → agent wake → **analyst interrupt** | **Never cut. This is the product.** |
| 3:15–3:50 | Both agents (LLM calls, lens prompts) | — |
| 3:50–4:15 | Workbench panes + revision inbox | Graph view is the upgrade, not the base |
| 4:15–4:30 | Rehearse the interrupt end to end | — |
| 4:30–5:00 | Record 60s video, push public repo, submit | — |

**Stretch if ahead at 4:15:** capability routing (§5.3), or ElevenLabs voicing the interrupt — separate prize, own criteria.

**Hard rules:** repo public · no code before 1:30 · video must clearly identify what was built in-window.

---

## 8. The 60-second video

Round One judging is **asynchronous on video + repo**. You never demo live unless you make top six. The video is the gate. It now has a protagonist — use them.

| Seconds | Frame |
|---|---|
| 0–8 | "Every memory system stores what happened. None store *why the analyst decided.*" |
| 8–20 | Analyst submits six sites, $40M allocated. Open one conclusion — premises, sources, expiries. |
| 20–32 | Analyst moves on to Site 4. Engineering strip flickers. **Interrupt fires unbidden.** |
| 32–48 | Revision inbox: three conclusions stale across both agents. Allocation re-sorts. Nobody clicked anything. |
| 48–60 | "One agent's conclusion is the other's premise. Change streams and `$graphLookup` do the rest." |

Zero preamble. No team intros. No architecture slide.

---

## 9. Data sourcing

**Real, and driving the cascade:**
LCFS credit prices (CARB / Argus / EcoEngineers) · PG&E BEV tariff sheet · NFPA 855 2026 thresholds · **GeoTracker / EnviroStor** (CA cleanup sites, address-searchable — *highest-value real fact available*) · DataSF parcel data (lot size, zoning) · PG&E ICA hosting capacity (real for 1–2 sites, modeled elsewhere)

**Modeled, and labeled as modeled:**
Existing service size, switchgear condition, structural capacity. These require a site visit and do not exist publicly.

Every premise carries `source` and `confidence`. An agent that knows which inputs are measured versus assumed is strictly more sophisticated than one that doesn't — and calibration keys off exactly that. **Say this in the demo rather than hiding it.**

---

## 10. Verify before saying on stage

**Sourced this session:** LCFS price series and Q3 2025 deficit · interconnection cost/timeline ranges · PG&E BEV subscription structure · Rule 29 service limits · NFPA 855 2026 HMA threshold · EPA reuse-based cleanup standards.

**Not verified — check first:** Rule 21 specifics · RA 4-hour duration requirement · current ITC rules and adders for standalone storage · SGIP window status · specific NFPA 855 setback distances · any square-footage figures.
