from collections import Counter, defaultdict
from datetime import datetime, timezone
import math

from .data import finite
from .pricing import ev, kelly

ALLOCATION_VERSION = "equal-share-v1"


def classify(row, config):
    reasons = []
    if row["expected_value_per_unit"] <= 0:
        reasons.append("PRICE_TOO_SHORT")
    if row["probability_edge_pp"] < config.min_edge_pp:
        reasons.append("EDGE_TOO_SMALL")
    if row["p_positive_ev"] < config.min_p_positive_ev or row["posterior_upper"]-row["posterior_lower"] > config.max_interval_width:
        reasons.append("UNCERTAINTY_HIGH")
    if row["historical_bets"] < config.min_sample:
        reasons.append("SMALL_SAMPLE")
    if row.get("historical_hr_rate") is not None and row["historical_hr_rate"] <= row["break_even_probability"]:
        reasons.append("SIGNAL_HISTORY_WEAK_AT_PRICE")
    if config.require_confirmed and row.get("lineup_status") != "confirmed":
        reasons.append("LINEUP_UNCONFIRMED")
    if row.get("model_probability_missing"):
        reasons.append("BASE_MODEL_MISSING")
    if not row["signal_families"]:
        reasons.append("UNMAPPED_SIGNAL")
    try:
        observed = datetime.fromisoformat(str(row.get("odds_observed") or "").replace("Z","+00:00"))
        age = (datetime.now(timezone.utc)-observed).total_seconds()/60
        if age > config.max_quote_age_minutes or age < -1:
            reasons.append("STALE_PRICE")
    except (ValueError, TypeError):
        reasons.append("PRICE_TIME_UNKNOWN")
    start = str(row.get("start_time") or "")
    try:
        if datetime.fromisoformat(start.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            reasons.append("GAME_STARTED")
    except (ValueError, TypeError):
        reasons.append("GAME_TIME_UNKNOWN")
    decision = "BET" if not reasons else "MARGINAL / WATCH" if row["expected_value_per_unit"] > 0 else "PASS"
    if "GAME_STARTED" in reasons or "GAME_TIME_UNKNOWN" in reasons:
        decision = "PASS"
    return decision, reasons


def allocate(rows, config, bankroll, existing=()):
    exposure = defaultdict(float)
    existing_players = set()
    def dimensions(row):
        return [("daily", "all"), ("bankroll", "all"),
                ("game", row.get("game_id") or "Unknown"), ("team", row.get("team") or "Unknown")] + \
               [("family", f) for f in sorted(set(row["signal_families"]))] + \
               [("model", f) for f in sorted(set(row["model_families"]))]
    for r in existing:
        existing_players.add(r["player_key"])
        for dimension in dimensions(r):
            exposure[dimension] += r["actual_units_bet"]
    limits = dict(daily=config.max_daily, bankroll=bankroll, game=config.max_game,
                  team=config.max_team, family=config.max_family, model=config.max_model)
    def cents(value):
        return math.floor(max(0., value) * 100 + 1e-9)

    capacity = {}
    candidates = []
    ordered = sorted(rows, key=lambda x: (-x["p_positive_ev"], -x["expected_value_per_unit"], x["player_key"]))
    for r in ordered:
        r["kelly_full"] = kelly(r["estimated_hr_probability"], r["american_odds"])
        r["kelly_fraction_used"] = config.kelly_fraction
        r["kelly_fractional"] = r["kelly_full"]*config.kelly_fraction
        r["recommended_units"] = 0.
        r["stake_caps_applied"] = []
        if r["player_key"] in existing_players:
            r["decision"] = "PASS"
            r["reasons"].insert(0, "ALREADY_RECORDED")
        if r["decision"] == "BET":
            proposed = bankroll*r["kelly_fractional"]
            dims = dimensions(r)
            for dimension in dims:
                capacity[dimension] = cents(limits[dimension[0]] - exposure[dimension])
            candidates.append(dict(row=r, dimensions=dims, proposed=proposed,
                                   ceiling=cents(min(proposed, config.max_stake)), allocated=0))

    # Raise each eligible stake equally until an individual or shared cap binds.
    # Whole cents prevent over-allocation; leftover cents follow the stable quality order.
    def headroom(item):
        return min([item["ceiling"] - item["allocated"]] + [capacity[d] for d in item["dimensions"]])

    while active := [item for item in candidates if headroom(item) > 0]:
        counts = Counter(d for item in active for d in item["dimensions"])
        step = min([item["ceiling"] - item["allocated"] for item in active] +
                   [capacity[d] // count for d, count in counts.items()])
        for item in active:
            amount = step if step else min(1, headroom(item))
            item["allocated"] += amount
            for dimension in item["dimensions"]:
                capacity[dimension] -= amount

    for item in candidates:
        r = item["row"]
        r["recommended_units"] = item["allocated"] / 100
        if r["recommended_units"] < item["proposed"]:
            caps = {kind for kind, value in item["dimensions"] if capacity[(kind, value)] == 0}
            if config.max_stake < item["proposed"]:
                caps.add("single bet")
            if len(candidates) > 1 and 0 < item["allocated"] < item["ceiling"]:
                caps.add("shared allocation")
            r["stake_caps_applied"] = sorted(caps)
        if not item["allocated"]:
            r["decision"] = "MARGINAL / WATCH"
            r["reasons"].insert(0, "PORTFOLIO_CONCENTRATION")

    for r in ordered:
        r["stake_cap_applied"] = bool(r["stake_caps_applied"])
        r["primary_reason"] = r["reasons"][0] if r["reasons"] else "MARGIN_OF_SAFETY_MET"
        r["explanation"] = (f"{r['decision']}: {r['american_odds']:+.0f} requires {r['break_even_probability']:.1%}. "
                            f"Final HR probability {r['estimated_hr_probability']:.1%}; edge {r['probability_edge_pp']:+.1f} pp; "
                            f"P(EV > 0) {r['p_positive_ev']:.1%}. {r['independent_family_count']} distinct families; "
                            f"{r['historical_bets']} price/quality-matched player-days. "
                            f"Stake {r['recommended_units']:.2f}u. " + "; ".join(r["reasons"]+r["stake_caps_applied"]))
    return rows


def unrecorded_decisions(rows, existing):
    recorded = {row["player_key"] for row in existing}
    return [row for row in rows if row["player_key"] not in recorded]


def needs_refresh(rows, config):
    """Expire current recommendations without changing frozen historical decisions."""
    temporal = {"STALE_PRICE", "PRICE_TIME_UNKNOWN", "GAME_STARTED", "GAME_TIME_UNKNOWN"}
    return any((set(classify(row, config)[1]) & temporal) - set(row.get("reasons", [])) for row in rows)
