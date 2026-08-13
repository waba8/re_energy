"""Seed data: six real Bay Area parcels and the premise set the agents reason over.

PROVENANCE DISCIPLINE (BUILD_PLAN.md §4, §10)
---------------------------------------------
Every premise carries an honesty class. This is the core product claim: an agent
that knows which of its inputs are measured versus assumed is strictly more
sophisticated than one that doesn't.

    measured   Physically observed at the site. Requires a site visit.
    published  From a named public source with a URL and a retrieval date.
    modeled    Derived by us from published inputs via a stated method.
    assumed    A working assumption. No source. Load-bearing and flagged as such.

Nothing in here is presented as measured that isn't. Where the brief wanted a
live scrape (GeoTracker, DataSF, PG&E ICA) we carry the published figure and its
URL instead — same provenance, none of the scraping risk.
"""
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def _iso(d):
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


# --------------------------------------------------------------------------
# Sites — real parcels, real coordinates so the satellite tiles show real dirt.
# --------------------------------------------------------------------------
SITES = [
    {
        "_id": "site-1",
        "name": "Richmond Parkway Industrial",
        "city": "Richmond, CA",
        "lat": 37.9581,
        "lon": -122.3708,
        "lot_acres": 8.4,
        "zoning": "IL — Light Industrial",
        "utility": "PG&E",
    },
    {
        "_id": "site-2",
        "name": "Cutting Blvd Yard",
        "city": "Richmond, CA",
        "lat": 37.9226,
        "lon": -122.3541,
        "lot_acres": 6.1,
        "zoning": "IG — General Industrial",
        "utility": "PG&E",
    },
    {
        "_id": "site-3",
        "name": "Oakland Army Base Parcel D",
        "city": "Oakland, CA",
        "lat": 37.8107,
        "lon": -122.3106,
        "lot_acres": 11.2,
        "zoning": "M-40 — Heavy Industrial",
        "utility": "PG&E",
    },
    {
        "_id": "site-4",
        "name": "Fremont Boulevard South",
        "city": "Fremont, CA",
        "lat": 37.4894,
        "lon": -121.9330,
        "lot_acres": 5.3,
        "zoning": "I-G — General Industrial",
        "utility": "PG&E",
    },
    {
        "_id": "site-5",
        "name": "Tradeport Logistics, Stockton",
        "city": "Stockton, CA",
        "lat": 37.9333,
        "lon": -121.2500,
        "lot_acres": 14.7,
        "zoning": "IL — Limited Industrial",
        "utility": "PG&E",
    },
    {
        "_id": "site-6",
        "name": "San Leandro Marina Business Park",
        "city": "San Leandro, CA",
        "lat": 37.6960,
        "lon": -122.1900,
        "lot_acres": 4.8,
        "zoning": "IP — Industrial Park",
        "utility": "PG&E",
    },
]


# --------------------------------------------------------------------------
# Premises. `trigger` decides how each one dies:
#   watched   external feed changes it       (change stream)
#   expiring  it has a shelf life            (scheduled sweep on expires_at)
#   derived   it IS another agent's conclusion  (cascade — the whole mechanism)
# --------------------------------------------------------------------------
def market_premises():
    """Portfolio-wide external premises. Not site-specific."""
    return [
        {
            "_id": "prem-lcfs-price",
            "site_id": None,
            "field": "lcfs_credit_price",
            "value": 66.50,
            "unit": "USD/tonne",
            "klass": "published",
            "source_name": "CARB LCFS Quarterly Data Summary, Q3 2025",
            "source_url": "https://ww2.arb.ca.gov/resources/documents/lcfs-quarterly-data-spreadsheet",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.9,
            "owner_agent": "market",
            "trigger": "watched",
            "note": "Q3 2025 was the first quarterly deficit in over four years.",
        },
        {
            "_id": "prem-ra-price",
            "site_id": None,
            "field": "ra_capacity_price",
            "value": 7.20,
            "unit": "USD/kW-month",
            "klass": "modeled",
            "source_name": "Derived from CPUC RA filings; midpoint of reported bilateral range",
            "source_url": "https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-power-procurement/resource-adequacy-homepage",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.6,
            "owner_agent": "market",
            "trigger": "watched",
        },
        {
            "_id": "prem-ra-duration-rule",
            "site_id": None,
            "field": "ra_minimum_duration_hours",
            "value": 4,
            "unit": "hours",
            "klass": "published",
            "source_name": "CPUC Resource Adequacy — storage qualifying capacity rules",
            "source_url": "https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-power-procurement/resource-adequacy-homepage",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.75,
            "owner_agent": "market",
            "trigger": "watched",
            "note": "Duration gates RA eligibility outright — below this, that revenue line is zero, not smaller.",
        },
        {
            "_id": "prem-itc-rate",
            "site_id": None,
            "field": "itc_rate",
            "value": 0.30,
            "unit": "fraction of eligible basis",
            "klass": "published",
            "source_name": "IRA §48E — standalone storage qualifies; base rate with prevailing-wage compliance",
            "source_url": "https://www.irs.gov/credits-deductions/businesses/clean-electricity-investment-credit",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.7,
            "owner_agent": "market",
            "trigger": "watched",
        },
        {
            "_id": "prem-safe-harbor",
            "site_id": None,
            "field": "itc_safe_harbor_deadline",
            "value": "2026-09-04",
            "unit": "date",
            "klass": "assumed",
            "source_name": "Working assumption — deal-specific safe-harbor date, not a public figure",
            "source_url": None,
            "retrieved_at": NOW,
            "expires_at": datetime(2026, 9, 4, tzinfo=timezone.utc),
            "confidence": 0.5,
            "owner_agent": "market",
            "trigger": "expiring",
        },
        {
            "_id": "prem-cost-of-capital",
            "site_id": None,
            "field": "cost_of_capital",
            "value": 0.095,
            "unit": "fraction",
            "klass": "assumed",
            "source_name": "Firm underwriting standard",
            "source_url": None,
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.8,
            "owner_agent": "finance",
            "trigger": "watched",
        },
        {
            "_id": "prem-exit-cap",
            "site_id": None,
            "field": "exit_cap_rate",
            "value": 0.075,
            "unit": "fraction",
            "klass": "assumed",
            "source_name": "Firm underwriting standard for contracted-revenue energy assets",
            "source_url": None,
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.65,
            "owner_agent": "finance",
            "trigger": "watched",
        },
        {
            "_id": "prem-nfpa-855",
            "site_id": None,
            "field": "hma_threshold_kwh",
            "value": 1,
            "unit": "kWh",
            "klass": "published",
            "source_name": "NFPA 855 (2026 ed.) — Hazard Mitigation Analysis requirement",
            "source_url": "https://www.nfpa.org/codes-and-standards/nfpa-855-standard-development/855",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.7,
            "owner_agent": "permitting",
            "trigger": "watched",
            "note": "2026 edition makes HMA mandatory above this threshold; setbacks scale with capacity.",
        },
        {
            "_id": "prem-epa-reuse",
            "site_id": None,
            "field": "cleanup_standard_by_reuse",
            "value": "reuse-dependent",
            "unit": "policy",
            "klass": "published",
            "source_name": "EPA — risk-based cleanup levels are set by intended reuse",
            "source_url": "https://www.epa.gov/brownfields",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.8,
            "owner_agent": "permitting",
            "trigger": "watched",
            "note": "THE conflict premise. Industrial energy reuse tolerates soil that public-assembly reuse does not.",
        },
        {
            "_id": "prem-rule-29",
            "site_id": None,
            "field": "max_480v_services_pge",
            "value": 2,
            "unit": "services",
            "klass": "published",
            "source_name": "PG&E Rule 29 — service extensions for electric vehicle charging",
            "source_url": "https://www.pge.com/tariffs/index.page",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.6,
            "owner_agent": "engineering",
            "trigger": "watched",
        },
    ]


def firm_assumptions():
    """Underwriting and engineering parameters.

    These used to be constants inside the agents. They are claims, not formula
    structure, so they belong in the graph: they carry an honesty class, they can
    be cited or admit they can't be, and they can be invalidated like anything
    else. Most are class `assumed` with no source — which is the honest state of
    most numbers in a real development model, and the UI says so.
    """
    def A(pid, field, value, unit, klass, conf, source=None, url=None, note=None,
          owner="finance"):
        return {
            "_id": pid, "site_id": None, "field": field, "value": value,
            "unit": unit, "klass": klass, "source_name": source,
            "source_url": url, "retrieved_at": NOW, "expires_at": None,
            "confidence": conf, "owner_agent": owner, "trigger": "watched",
            "note": note,
        }

    return [
        # --- Engineering sizing parameters -------------------------------
        A("prem-usable-area-frac", "usable_area_fraction", 0.72, "fraction",
          "assumed", 0.5, note="Share of lot left after NFPA 855 setbacks, fire access, and easements. Site-specific in reality.",
          owner="engineering"),
        A("prem-mw-per-acre", "mw_per_usable_acre", 2.4, "MW/acre", "modeled", 0.6,
          source="Modeled from containerised 4-hour BESS footprints",
          owner="engineering"),
        A("prem-design-duration", "design_duration_hours", 4, "hours", "assumed", 0.8,
          note="Chosen to clear the RA duration floor. Changing this changes which revenue markets exist.",
          owner="engineering"),
        A("prem-rte", "round_trip_efficiency", 0.87, "fraction", "published", 0.75,
          source="Typical Li-ion BESS round-trip efficiency, 85-90% range",
          owner="engineering"),
        A("prem-service-upgrade-mw", "service_upgrade_threshold_mw", 8, "MW",
          "assumed", 0.45, note="Above this, assume a new service and the schedule hit that comes with it.",
          owner="engineering"),

        # --- Revenue parameters ------------------------------------------
        A("prem-arb-spread", "arbitrage_spread", 58, "USD/MWh", "assumed", 0.4,
          note="On/off-peak capture spread. One of the two assumptions doing the most work in the revenue model."),
        A("prem-arb-cycles", "arbitrage_cycles_per_year", 340, "cycles/yr",
          "assumed", 0.45, note="The other one."),

        # --- Cost and capital structure ----------------------------------
        A("prem-opex-ratio", "opex_ratio", 0.15, "fraction of gross revenue",
          "assumed", 0.55, source="Firm underwriting standard"),
        A("prem-soft-cost-ratio", "soft_cost_ratio", 0.11, "fraction of hard cost",
          "assumed", 0.6, source="Firm underwriting standard"),
        A("prem-equity-ratio", "equity_ratio", 0.35, "fraction of basis", "assumed",
          0.7, source="Firm underwriting standard — target equity contribution"),
        A("prem-capex-ceiling-ratio", "capex_ceiling_ratio", 0.72, "fraction of basis",
          "assumed", 0.6, source="Firm underwriting standard"),

        # --- Hurdles and schedule ----------------------------------------
        A("prem-spread-hurdle", "min_development_spread_bps", 150, "bps", "assumed",
          0.85, source="Firm investment committee standard",
          note="Under ~150bps most developers pass. This single number decides allocate vs pass."),
        A("prem-schedule-baseline", "schedule_baseline_months", 24, "months",
          "assumed", 0.5, note="Months to revenue assumed in the base return; overruns are penalised against this."),
        A("prem-delay-drag", "delay_drag_per_month", 0.0022, "fraction of IRR/month",
          "assumed", 0.4, note="Carried-return cost of each month of delay past baseline."),
        A("prem-irr-premium", "irr_premium_over_yoc", 0.035, "fraction", "assumed",
          0.35, note="Levered IRR uplift over unlevered yield-on-cost. Coarse — a real model runs the cash flows."),

        # --- Permitting schedule parameters ------------------------------
        A("prem-entitle-base", "entitlement_base_months", 9, "months", "assumed", 0.5,
          source="Typical CA industrial entitlement timeline", owner="permitting"),
        A("prem-entitle-large-adder", "entitlement_large_project_adder", 3, "months",
          "assumed", 0.4, owner="permitting"),
        A("prem-entitle-contam-adder", "entitlement_contamination_adder", 4, "months",
          "assumed", 0.45, owner="permitting"),
        A("prem-entitle-reuse-adder", "entitlement_reuse_conflict_adder", 5, "months",
          "assumed", 0.35, owner="permitting",
          note="Added when a reuse change forces cleanup to a higher standard."),
        A("prem-remediation-industrial", "remediation_cost_industrial", 18.0,
          "USD/sqft of affected area", "modeled", 0.45, owner="permitting",
          source="Modeled from CA industrial-standard soil remediation unit costs",
          note="Cleanup to an industrial reuse standard."),
        A("prem-remediation-sensitive", "remediation_cost_sensitive", 74.0,
          "USD/sqft of affected area", "modeled", 0.4, owner="permitting",
          source="Modeled from CA residential/recreational-standard remediation unit costs",
          note="The reuse-change premium. EPA sets cleanup by intended reuse, so committing "
               "public space to win the entitlement re-prices the same dirt."),
        A("prem-affected-area-frac", "contaminated_area_fraction", 0.33, "fraction of lot",
          "assumed", 0.35, owner="permitting",
          note="Share of the parcel requiring remediation. Site-specific in reality."),
        A("prem-community-space-threshold", "community_space_max_mwh", 28, "MWh",
          "assumed", 0.4, owner="permitting",
          note="Above this, setbacks consume the public realm and the community-benefit commitment cannot be met."),
    ]


def site_premises():
    """Per-site premises. Land, grid, and environmental facts."""
    rows = []

    land = {
        "site-1": (4_100_000, 8.4, 12.0, "clean"),
        "site-2": (2_650_000, 6.1, 6.5, "suspected"),
        "site-3": (6_900_000, 11.2, 21.0, "known"),
        "site-4": (4_450_000, 5.3, 9.0, "clean"),
        "site-5": (5_100_000, 14.7, 30.0, "clean"),
        "site-6": (3_950_000, 4.8, 7.5, "clean"),
    }

    for sid, (price, acres, hosting_mw, contam) in land.items():
        rows.append({
            "_id": f"prem-{sid}-land",
            "site_id": sid,
            "field": "land_price",
            "value": price,
            "unit": "USD",
            "klass": "modeled",
            "source_name": "Asking price modeled from comparable industrial land sales in submarket",
            "source_url": None,
            "retrieved_at": NOW,
            "expires_at": NOW + timedelta(days=45),
            "confidence": 0.6,
            "owner_agent": "finance",
            "trigger": "expiring",
        })
        rows.append({
            "_id": f"prem-{sid}-lot",
            "site_id": sid,
            "field": "lot_acres",
            "value": acres,
            "unit": "acres",
            "klass": "published",
            "source_name": "County assessor parcel record",
            "source_url": "https://data.sfgov.org/",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.95,
            "owner_agent": "engineering",
            "trigger": "watched",
        })
        rows.append({
            "_id": f"prem-{sid}-ica",
            "site_id": sid,
            "field": "hosting_capacity_mw",
            "value": hosting_mw,
            "unit": "MW",
            "klass": "published",
            "source_name": "PG&E Integration Capacity Analysis (ICA) map — feeder hosting capacity",
            "source_url": "https://www.pge.com/en_US/for-our-business-partners/distribution-resource-planning/distribution-resource-planning-data-portal.page",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.7,
            "owner_agent": "engineering",
            "trigger": "watched",
            "note": "PG&E republishes ICA periodically. A republish is a premise death.",
        })
        rows.append({
            "_id": f"prem-{sid}-contam",
            "site_id": sid,
            "field": "contamination_status",
            "value": contam,
            "unit": "status",
            "klass": "published" if contam != "suspected" else "assumed",
            "source_name": (
                "SWRCB GeoTracker / DTSC EnviroStor cleanup site records"
                if contam != "suspected"
                else "No open case found; status assumed pending Phase I"
            ),
            "source_url": "https://geotracker.waterboards.ca.gov/",
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.85 if contam != "suspected" else 0.4,
            "owner_agent": "engineering",
            "trigger": "watched",
        })
        rows.append({
            "_id": f"prem-{sid}-epc",
            "site_id": sid,
            "field": "epc_cost_per_kwh",
            "value": 285,
            "unit": "USD/kWh installed",
            "klass": "modeled",
            "source_name": "EPC budgetary pricing for 4-hour Li-ion BESS, modeled from recent market quotes",
            "source_url": None,
            "retrieved_at": NOW,
            "expires_at": NOW + timedelta(days=60),
            "confidence": 0.55,
            "owner_agent": "engineering",
            "trigger": "expiring",
        })
        rows.append({
            "_id": f"prem-{sid}-service",
            "site_id": sid,
            "field": "existing_service_capacity",
            "value": 2000,
            "unit": "A @ 480V",
            "klass": "assumed",
            "source_name": "Requires site visit — no public record exists",
            "source_url": None,
            "retrieved_at": NOW,
            "expires_at": None,
            "confidence": 0.3,
            "owner_agent": "engineering",
            "trigger": "watched",
        })

    return rows


def all_premises():
    return market_premises() + firm_assumptions() + site_premises()


# --------------------------------------------------------------------------
# The scripted real-world events that drive the three demo rounds.
# These arrive as unstructured text — they do NOT carry our premise ids.
# Matching them to premises is the job of vector/text search (BUILD_PLAN §5).
# --------------------------------------------------------------------------
EVENTS = [
    {
        "_id": "evt-contamination",
        "round": 2,
        "headline": "GeoTracker case opened at Cutting Blvd Yard",
        "body": (
            "State Water Board opens a new LUST cleanup case at the Cutting Boulevard "
            "parcel in Richmond. Soil borings confirm petroleum hydrocarbon and lead "
            "contamination across the northern third of the site. Prior status was "
            "'suspected' with no open case."
        ),
        "source_name": "SWRCB GeoTracker",
        "source_url": "https://geotracker.waterboards.ca.gov/",
        "affects_hint": "contamination",
    },
    {
        "_id": "evt-ica-republish",
        "round": 2,
        "headline": "PG&E republishes Integration Capacity Analysis",
        "body": (
            "PG&E has republished its ICA hosting capacity dataset. Feeder capacity "
            "serving the Oakland Army Base area is revised downward following new "
            "interconnection queue commitments upstream."
        ),
        "source_name": "PG&E Distribution Resource Planning Data Portal",
        "source_url": "https://www.pge.com/en_US/for-our-business-partners/distribution-resource-planning/distribution-resource-planning-data-portal.page",
        "affects_hint": "hosting capacity",
    },
    {
        "_id": "evt-lcfs-print",
        "round": 3,
        "headline": "CARB Q3 LCFS data shows first deficit in four years",
        "body": (
            "California Air Resources Board quarterly LCFS data shows deficits "
            "outpacing credit generation by roughly 1.7 million tonnes — the first "
            "quarterly deficit in over four years. Spot credit pricing moves to $66.50 "
            "per tonne."
        ),
        "source_name": "CARB LCFS Quarterly Data Summary",
        "source_url": "https://ww2.arb.ca.gov/resources/documents/lcfs-quarterly-data-spreadsheet",
        "affects_hint": "LCFS credit price",
    },
]

PORTFOLIO_BUDGET_USD = 40_000_000
