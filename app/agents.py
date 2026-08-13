"""The three agents.

Division of labour, and it is deliberate: the LLM makes judgments, the ledger
does arithmetic. Language models are bad calculators and good analysts, so
Engineering/Permitting/Finance use the model for the qualitative calls — is this
contamination gating, which entitlement path applies, does this deal clear — and
compute basis, yield, and spread in Python where the numbers are reproducible.

Every agent must declare `depends_on` for each conclusion it emits. An agent that
cannot say what its answer rests on cannot participate in the cascade, so this is
enforced structurally rather than by prompt discipline.
"""
import json
import os

import httpx

from . import db, graph

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")


def _key():
    for k in ("OPEN_ROUTER_API_KEY", "OPEN_ROUTER_API_KEY ", "OPENROUTER_API_KEY"):
        v = os.environ.get(k)
        if v:
            return v.strip().strip('"').strip("'")
    return None


async def reason(system: str, user: str, schema_hint: str, fallback: dict) -> dict:
    """Ask the model for a judgment as JSON. Fall back to a stated default.

    The fallback is not a hack — a demo that dies because an inference endpoint
    hiccuped is a demo that doesn't get recorded. Every fallback is a value we
    would defend on its own, and `llm` records which path was taken.
    """
    key = _key()
    if not key:
        return {**fallback, "llm": False}

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system + "\n\nRespond with JSON only, matching:\n" + schema_hint},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.startswith("json") else text
        out = json.loads(text.strip())
        return {**fallback, **out, "llm": True}
    except Exception as e:
        return {**fallback, "llm": False, "llm_error": str(e)[:160]}


async def premise_map(site_id):
    """Active premises visible to an agent for one site, plus portfolio-wide ones."""
    rows = await db.premises().find({
        "status": {"$ne": "superseded"},
        "$or": [{"site_id": site_id}, {"site_id": None}],
    }).to_list(length=None)
    out = {}
    for r in rows:
        # Prefer the site-specific premise when a field exists at both levels.
        if r["field"] not in out or r.get("site_id"):
            out[r["field"]] = r
    return out


def _brief(p):
    if not p:
        return "unavailable"
    return f"{p.get('value')} {p.get('unit','')} [{p.get('klass')}, conf {p.get('confidence')}]"


class Reader:
    """Reads premise values and records every dependency it touched.

    Nothing numeric should reach a formula without passing through here. If a
    parameter is worth putting in a formula it is worth being able to cite, to
    expire, and to invalidate — and an agent that reads a value without
    registering the edge silently drops out of the cascade.
    """

    def __init__(self, premises: dict):
        self.P = premises
        self.used: list[str] = []

    def get(self, field, default=None):
        p = self.P.get(field)
        if not p:
            return default
        if p["_id"] not in self.used:
            self.used.append(p["_id"])
        return p.get("value")

    def num(self, field, default=0.0):
        v = self.get(field, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float(default)

    def premise(self, field):
        """Touch a premise for its metadata without pretending to read a number."""
        p = self.P.get(field)
        if p and p["_id"] not in self.used:
            self.used.append(p["_id"])
        return p

    @property
    def depends_on(self):
        return list(self.used)


# ---------------------------------------------------------------------------
# ENGINEERING — what can this dirt physically hold
# ---------------------------------------------------------------------------
async def run_engineering(site, round_no):
    sid = site["_id"]
    P = await premise_map(sid)

    R = Reader(P)
    ica, lot = R.premise("hosting_capacity_mw"), R.premise("lot_acres")
    epc, contam = R.premise("epc_cost_per_kwh"), R.premise("contamination_status")
    ceiling = R.premise("capex_ceiling")  # derived from Finance — the back-edge

    hosting = R.num("hosting_capacity_mw", 10.0)
    acres = R.num("lot_acres", 5.0)

    # Footprint-limited MW = usable acreage × density. The formula is structure;
    # both parameters are premises because both are contestable.
    footprint_mw = acres * R.num("usable_area_fraction", 0.72) * R.num("mw_per_usable_acre", 2.4)
    max_mw = round(min(hosting, footprint_mw), 1)
    duration = R.num("design_duration_hours", 4)
    max_mwh = round(max_mw * duration, 1)

    unit_cost = R.num("epc_cost_per_kwh", 285)
    if ceiling:
        affordable_mwh = R.num("capex_ceiling") / (unit_cost * 1000)
        if affordable_mwh < max_mwh:
            max_mwh = round(affordable_mwh, 1)
            max_mw = round(max_mwh / duration, 1)

    upgrade_threshold = R.num("service_upgrade_threshold_mw", 8)
    depends = R.depends_on

    judgment = await reason(
        system=(
            "You are the engineering agent on a battery storage development team. "
            "You size systems against feeder hosting capacity, buildable area after "
            "NFPA 855 setbacks, and interconnection constraints. You read soil "
            "contamination as an ENERGY use would: industrial reuse tolerates soil "
            "that public assembly would not, and contamination is often why the land "
            "is cheap. Be terse and technical."
        ),
        user=(
            f"Site: {site['name']}, {site['city']}. {acres} acres, zoned {site['zoning']}.\n"
            f"Feeder hosting capacity: {_brief(ica)}\n"
            f"Contamination status: {_brief(contam)}\n"
            f"EPC cost: {_brief(epc)}\n"
            f"Capex ceiling from finance: {_brief(ceiling)}\n"
            f"Your sizing: {max_mw} MW / {max_mwh} MWh, {duration}-hour duration.\n\n"
            "In two sentences, justify this configuration and name the binding constraint."
        ),
        schema_hint='{"reasoning": str, "binding_constraint": str, "service_upgrade_required": bool, "months_to_energization": int}',
        fallback={
            "reasoning": (
                f"Sized to {max_mw} MW / {max_mwh} MWh. Binding constraint is "
                + ("feeder hosting capacity" if hosting < footprint_mw else "buildable area after setbacks")
                + "."
            ),
            "binding_constraint": "hosting capacity" if hosting < footprint_mw else "buildable area",
            "service_upgrade_required": max_mw > upgrade_threshold,
            "months_to_energization": 18 if max_mw <= upgrade_threshold else 26,
        },
    )

    capex = round(max_mwh * 1000 * unit_cost)

    out = []
    for field, value, unit in (
        ("max_mw", max_mw, "MW"),
        ("max_mwh", max_mwh, "MWh"),
        ("duration_hours", duration, "hours"),
        ("capex", capex, "USD"),
        ("months_to_energization", judgment["months_to_energization"], "months"),
    ):
        cid, pid = await graph.publish_conclusion(
            agent="engineering", site_id=sid, field=field, value=value, unit=unit,
            reasoning=judgment["reasoning"], depends_on=depends, round_no=round_no,
            extra={"binding_constraint": judgment.get("binding_constraint"),
                   "llm": judgment.get("llm", False)},
        )
        out.append(cid)
    return out


# ---------------------------------------------------------------------------
# PERMITTING — the same facts, read by someone who has to get this approved
# ---------------------------------------------------------------------------
async def run_permitting(site, round_no):
    """Reads Engineering's output as its premise, and disagrees with it.

    This agent exists to make the brief's §2.5 insight produce behaviour instead
    of prose: EPA sets cleanup standards by intended reuse, so the community
    space that carries the entitlement path is exactly what makes contaminated
    soil expensive. Engineering never sees that, because it isn't looking.
    """
    sid = site["_id"]
    P = await premise_map(sid)

    R = Reader(P)
    mwh = R.premise("max_mwh")
    contam = R.premise("contamination_status")
    reuse = R.premise("cleanup_standard_by_reuse")
    hma = R.premise("hma_threshold_kwh")

    capacity_mwh = R.num("max_mwh", 0)
    contamination = str(R.get("contamination_status", "clean"))
    hma_required = capacity_mwh * 1000 > R.num("hma_threshold_kwh", 1)

    # Above the community-space threshold, setbacks consume the public realm and
    # the community-benefit commitment carrying the entitlement can't be met.
    community_space_committed = capacity_mwh < R.num("community_space_max_mwh", 28)
    reuse_conflict = contamination == "known" and community_space_committed

    base_months = R.num("entitlement_base_months", 9)
    if capacity_mwh > 30:
        base_months += R.num("entitlement_large_project_adder", 3)
    if contamination == "known":
        base_months += R.num("entitlement_contamination_adder", 4)
    if reuse_conflict:
        base_months += R.num("entitlement_reuse_conflict_adder", 5)
    base_months = int(base_months)

    # Remediation cost, priced against the standard the reuse actually triggers.
    # This is the edge that makes the conflict bite: schedule alone rarely kills a
    # deal, but re-pricing the same soil at the sensitive-reuse standard does.
    lot_sqft = R.num("lot_acres", 5.0) * 43_560
    affected = lot_sqft * R.num("contaminated_area_fraction", 0.33)
    if contamination == "clean":
        remediation = 0.0
    else:
        rate = (R.num("remediation_cost_sensitive", 74.0) if reuse_conflict
                else R.num("remediation_cost_industrial", 18.0))
        remediation = affected * rate * (1.0 if contamination == "known" else 0.4)

    depends = R.depends_on

    judgment = await reason(
        system=(
            "You are the permitting and preconstruction agent on a battery storage "
            "development team. You own entitlement path, CEQA exposure, fire code "
            "review, and the schedule to permit. Critically: EPA sets risk-based "
            "cleanup standards by INTENDED REUSE. If the project commits community "
            "or public-assembly space to win its entitlement, contaminated soil that "
            "an industrial energy use would tolerate now triggers a higher cleanup "
            "standard. Engineering will read contamination as good news. Your job is "
            "to say when it isn't. Be blunt and specific about schedule."
        ),
        user=(
            f"Site: {site['name']}, {site['city']}. Zoned {site['zoning']}.\n"
            f"Engineering sized: {_brief(mwh)}\n"
            f"Contamination: {_brief(contam)}\n"
            f"Community benefit space committed for entitlement: {community_space_committed}\n"
            f"NFPA 855 HMA required: {hma_required}\n\n"
            "State the entitlement path (by-right / CUP / CEQA), months to entitle, "
            "and whether a reuse-based cleanup standard is triggered. If it is, say "
            "plainly that engineering is reading the same fact backwards."
        ),
        schema_hint='{"reasoning": str, "entitlement_path": str, "months_to_entitle": int, "cleanup_standard_triggered": bool, "human_action": str}',
        fallback={
            "reasoning": (
                f"Contamination status '{contamination}'. "
                + ("Community-benefit space is committed for the entitlement path, which "
                   "makes this a reuse change — cleanup is assessed against the higher "
                   "standard, not the industrial one. Engineering scored this site as "
                   "cheap land; it is not cheap on this path."
                   if reuse_conflict else
                   "Industrial reuse standard applies. No reuse conflict.")
            ),
            "entitlement_path": "CEQA review" if reuse_conflict else ("CUP" if contamination != "clean" else "by-right"),
            "months_to_entitle": base_months,
            "cleanup_standard_triggered": reuse_conflict,
            "human_action": (
                f"Request a pre-application meeting with {site['city'].split(',')[0]} "
                "Planning to confirm the reuse determination before the safe-harbor date."
                if reuse_conflict else ""
            ),
        },
    )

    out = []
    for field, value, unit in (
        ("months_to_entitle", judgment["months_to_entitle"], "months"),
        ("entitlement_path", judgment["entitlement_path"], "path"),
        ("cleanup_standard_triggered", judgment["cleanup_standard_triggered"], "bool"),
        ("hma_required", hma_required, "bool"),
        ("remediation_cost", round(remediation), "USD"),
    ):
        cid, pid = await graph.publish_conclusion(
            agent="permitting", site_id=sid, field=field, value=value, unit=unit,
            reasoning=judgment["reasoning"], depends_on=depends, round_no=round_no,
            extra={"llm": judgment.get("llm", False)},
        )
        out.append(cid)

    # An action is raised only when the reuse conflict is genuinely live. Gating
    # on the model returning prose produced an action for every site, including
    # clean ones whose "action" was a sentence explaining there was no action.
    action = judgment.get("human_action") if reuse_conflict else None
    if action:
        await db.actions().replace_one(
            {"_id": f"act-{sid}-r{round_no}"},
            {
                "_id": f"act-{sid}-r{round_no}",
                "site_id": sid,
                "site_name": site["name"],
                "agent": "permitting",
                "action": action,
                "because": judgment["reasoning"],
                "status": "pending",
                "round": round_no,
                "created_at": graph.utcnow(),
            },
            upsert=True,
        )
    return out


# ---------------------------------------------------------------------------
# FINANCE — what it's worth, and where the $40M goes
# ---------------------------------------------------------------------------
async def run_finance(site, round_no):
    sid = site["_id"]
    P = await premise_map(sid)

    R = Reader(P)
    mw, mwh = R.premise("max_mw"), R.premise("max_mwh")
    duration, capex = R.premise("duration_hours"), R.premise("capex")
    energize = R.premise("months_to_energization")
    entitle = R.premise("months_to_entitle")
    land, ra_price = R.premise("land_price"), R.premise("ra_capacity_price")
    ra_min = R.premise("ra_minimum_duration_hours")
    exit_cap, itc = R.premise("exit_cap_rate"), R.premise("itc_rate")

    mw_v = R.num("max_mw", 0)
    dur_v = R.num("duration_hours", 0)
    capex_v = R.num("capex", 0)
    land_v = R.num("land_price", 0)
    ra_v = R.num("ra_capacity_price", 0)
    ra_min_v = R.num("ra_minimum_duration_hours", 4)
    cap_v = R.num("exit_cap_rate", 0.075)
    itc_v = R.num("itc_rate", 0.30)

    # Duration gates RA eligibility outright. Below the threshold this revenue
    # line is zero, not smaller — which is why it can flip a deal on its own.
    ra_eligible = dur_v >= ra_min_v
    ra_revenue = mw_v * 1000 * ra_v * 12 if ra_eligible else 0.0
    arbitrage = (mw_v * dur_v * 1000
                 * R.num("round_trip_efficiency", 0.87)
                 * R.num("arbitrage_spread", 58)
                 * R.num("arbitrage_cycles_per_year", 340) / 1000)
    gross = ra_revenue + arbitrage
    noi = gross * (1 - R.num("opex_ratio", 0.15))

    basis = (land_v + capex_v + capex_v * R.num("soft_cost_ratio", 0.11)
             + R.num("remediation_cost", 0))
    basis_after_itc = basis - (capex_v * itc_v)

    yoc = (noi / basis_after_itc) if basis_after_itc else 0
    spread_bps = (yoc - cap_v) * 10_000

    months = max(R.num("months_to_energization", 18), R.num("months_to_entitle", 9))
    delay_penalty = max(0.0, (months - R.num("schedule_baseline_months", 24))
                        * R.num("delay_drag_per_month", 0.0022))
    irr = max(0.0, yoc + R.num("irr_premium_over_yoc", 0.035) - delay_penalty)

    hurdle_bps = R.num("min_development_spread_bps", 150)
    passes = spread_bps >= hurdle_bps
    depends = R.depends_on

    judgment = await reason(
        system=(
            "You are the real estate finance agent underwriting battery storage "
            "development. Development spread is yield-on-cost minus exit cap; under "
            "roughly 150bps most firms pass. Schedule is not a soft factor — it hits "
            "IRR directly and can break ITC safe-harbor eligibility. Give a verdict "
            "with the specific reason. Be decisive, no hedging."
        ),
        user=(
            f"Site: {site['name']}, {site['city']}.\n"
            f"Configuration: {mw_v} MW / {dur_v}h. RA eligible: {ra_eligible}.\n"
            f"Basis after ITC: ${basis_after_itc:,.0f}. Stabilized NOI: ${noi:,.0f}.\n"
            f"Yield on cost: {yoc:.2%}. Exit cap: {cap_v:.2%}. Spread: {spread_bps:.0f}bps.\n"
            f"Longest path to revenue: {months:.0f} months "
            f"(energization {energize['value'] if energize else '?'}, "
            f"entitlement {entitle['value'] if entitle else '?'}).\n\n"
            "Verdict: allocate or pass, and why in one sentence."
        ),
        schema_hint='{"reasoning": str, "verdict": "allocate"|"pass", "capex_ceiling": number, "required_yield": number}',
        fallback={
            "reasoning": (
                f"Spread of {spread_bps:.0f}bps "
                + (f"clears the {hurdle_bps:.0f}bps hurdle." if passes
                   else f"is below the {hurdle_bps:.0f}bps hurdle.")
                + ("" if ra_eligible else " RA capacity revenue does not qualify at this duration.")
                + (f" {months:.0f}-month path to revenue is the binding drag." if months > 26 else "")
            ),
            "verdict": "allocate" if passes else "pass",
            "capex_ceiling": round(basis * R.num("capex_ceiling_ratio", 0.72)),
            "required_yield": R.num("cost_of_capital", 0.095),
        },
    )

    out = []
    for field, value, unit in (
        ("basis", round(basis_after_itc), "USD"),
        ("noi", round(noi), "USD/yr"),
        ("yield_on_cost", round(yoc, 4), "fraction"),
        ("development_spread_bps", round(spread_bps), "bps"),
        ("irr", round(irr, 4), "fraction"),
        ("verdict", judgment["verdict"], "verdict"),
        ("capex_ceiling", judgment["capex_ceiling"], "USD"),
    ):
        cid, pid = await graph.publish_conclusion(
            agent="finance", site_id=sid, field=field, value=value, unit=unit,
            reasoning=judgment["reasoning"], depends_on=depends, round_no=round_no,
            extra={"ra_eligible": ra_eligible, "llm": judgment.get("llm", False)},
        )
        out.append(cid)
    return out


AGENTS = {
    "engineering": run_engineering,
    "permitting": run_permitting,
    "finance": run_finance,
}
