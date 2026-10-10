import numpy as np
import pandas as pd
from scipy.stats import beta, norm
from scipy.special import logit

from .pricing import decimal_odds, break_even, ev


def strategy(frame, kind="sized"):
    if frame.empty:
        return frame.copy()
    f = frame.copy()
    if kind in {"filtered", "sized"}:
        f = f[f.decision.eq("BET")].copy()
    if f.empty:
        return f
    f["stake"] = f.actual_units_bet if kind == "actual" else f.recommended_units if kind == "sized" else 1.
    f = f[f.stake.gt(0)].copy()
    f["odds"] = f.actual_american_odds if kind == "actual" else f.american_odds
    f["p"] = pd.to_numeric(f.estimated_hr_probability, errors="coerce")
    f["q"] = f.odds.map(break_even)
    f["ev"] = [ev(p, o) for p,o in zip(f.p, f.odds)]
    f["edge"] = (f.p-f.q)*100
    if kind == "actual":
        def confidence(r):
            if pd.isna(r["p"]):
                return np.nan
            if str(r.get("probability_method") or "").startswith("Price/"):
                return beta.sf(r["q"],r["alpha"],r["beta"])
            mu, sd = r.get("latent_mu"), r.get("latent_sd")
            return norm.sf((logit(r["q"])-mu)/sd) if mu is not None and sd else np.nan
        f["p_positive_ev"] = f.apply(confidence, axis=1)
    f["expected_profit"] = f.stake*f.ev
    f["profit"] = [s*ev(y,o) if pd.notna(y) else 0 if r=="Void" else np.nan for s,y,o,r in zip(f.stake,f.result_hr,f.odds,f.result)]
    f["return_1u"] = f.profit/f.stake
    return f


def graded(frame):
    return frame[frame.result.isin(["HR","No HR"])].copy() if not frame.empty else frame.copy()


def timeline(frame, bankroll, window=20):
    f = graded(frame).copy()
    if not f.empty:
        f["_order"] = f.placed_at.fillna(f.recorded) if "placed_at" in f else f.recorded
        f = f.sort_values(["date", "_order", "player_key"]).drop(columns="_order")
    if f.empty:
        return f
    f["bet"] = np.arange(1,len(f)+1)
    f["cumulative_profit"] = f.profit.cumsum()
    if f.expected_profit.notna().any():
        f["cumulative_expected"] = f.expected_profit.fillna(0).cumsum()
    else:
        f["cumulative_expected"] = np.nan
    f["bankroll_before"] = bankroll + f.cumulative_profit - f.profit
    f["bankroll_after"] = bankroll + f.cumulative_profit
    f["peak"] = f.bankroll_after.cummax().clip(lower=bankroll)
    f["drawdown_units"] = f.bankroll_after-f.peak
    f["drawdown_percent"] = 100*f.drawdown_units/f.peak
    f["rolling_roi"] = f.profit.rolling(window, min_periods=window).sum()/f.stake.rolling(window,min_periods=window).sum()*100
    f["expected_hr"] = f.p.cumsum(skipna=False)
    f["market_expected_hr"] = f.q.cumsum()
    f["actual_hr"] = f.result_hr.cumsum()
    f["hr_residual"] = f.actual_hr-f.expected_hr
    f["market_residual"] = f.actual_hr-f.market_expected_hr
    f["pnl_residual"] = f.cumulative_profit-f.cumulative_expected
    return f


def summary(frame, bankroll=100, window=20):
    f = graded(frame)
    if f.empty:
        return {"bets":0,"hr":0,"units_risked":0,"profit":0,"current_bankroll":bankroll}
    t = timeline(f,bankroll,window)
    stake, profit = f.stake.sum(), f.profit.sum()
    returns = f.return_1u
    vol = returns.std(ddof=1)
    downside = np.sqrt(np.mean(np.minimum(returns,0)**2))
    peak_days, current_start, recovered = [], None, []
    for r in t.to_dict("records"):
        day = pd.Timestamp(r["date"])
        if r["drawdown_units"] < 0:
            current_start = current_start or day
            peak_days.append((day-current_start).days)
        elif current_start is not None:
            recovered.append((day-current_start).days)
            current_start = None
    losses = abs(f.loc[f.profit.lt(0),"profit"].sum())
    market_brier = ((f.result_hr-f.q)**2).mean()
    strabo_brier = ((f.result_hr-f.p)**2).mean()
    expected = f.expected_profit.sum() if f.expected_profit.notna().all() else None
    max_dd = abs(t.drawdown_percent.min())
    return dict(bets=len(f), hr=int(f.result_hr.sum()), hit_rate=f.result_hr.mean()*100,
                units_risked=stake, profit=profit, roi=profit/stake*100 if stake else None,
                current_bankroll=bankroll+profit, maximum_bankroll=t.peak.max(), total_return=profit/bankroll*100,
                max_drawdown=max_dd, current_drawdown=abs(t.drawdown_percent.iloc[-1]),
                longest_drawdown_days=max(peak_days,default=0), longest_recovery_days=max(recovered,default=None),
                avg_probability=f.p.mean()*100, avg_break_even=f.q.mean()*100, avg_edge=f.edge.mean(),
                avg_p_positive_ev=f.p_positive_ev.mean()*100, expected_profit=expected,
                pnl_residual=profit-expected if expected is not None else None, market_brier=market_brier, strabo_brier=strabo_brier,
                brier_improvement=market_brier-strabo_brier,
                brier_skill=1-strabo_brier/market_brier if market_brier else None,
                rolling_roi=t.rolling_roi.iloc[-1], avg_family_count=f.independent_family_count.mean(),
                profit_factor=f.loc[f.profit.gt(0),"profit"].sum()/losses if losses else None,
                average_return=returns.mean(), return_volatility=vol,
                sharpe_like=returns.mean()/vol if vol and np.isfinite(vol) else None,
                sortino_like=returns.mean()/downside if downside else None,
                calmar_like=(profit/bankroll*100)/max_dd if max_dd else None)


def calibration(frame):
    f = graded(frame)
    output = []
    if f.empty:
        return pd.DataFrame()
    bins = [0,.10,.125,.15,.175,.20,.225,1.00001]
    for model,column in [("Market break-even","q"),("Strabo final","p")]:
        g = f.assign(bin=pd.cut(f[column],bins,include_lowest=True))
        for label, sample in g.groupby("bin",observed=True):
            n, hits = len(sample), sample.result_hr.sum()
            low,high = beta.interval(.90,.5+hits,.5+n-hits)
            output.append(dict(model=model, bucket=str(label), bets=n, predicted=sample[column].mean()*100,
                               observed=hits/n*100, lower=low*100, upper=high*100))
    return pd.DataFrame(output)


def performance(frame, column):
    f = graded(frame)
    if f.empty:
        return pd.DataFrame()
    output = []
    for value,g in f.groupby(column,observed=True,sort=True):
        n = len(g)
        output.append(dict(group=str(value), bets=n, hr=int(g.result_hr.sum()), hr_rate=100*g.result_hr.mean(),
                           units=g.stake.sum(), profit=g.profit.sum(), roi=100*g.profit.sum()/g.stake.sum(),
                           predicted_hr_rate=g.p.mean()*100, market_rate=g.q.mean()*100,
                           predicted_bets=int(g.p.notna().sum()), expected_hr=g.p.sum(min_count=1), actual_minus_expected=(g.result_hr-g.p).sum(min_count=1),
                           actual_minus_market=(g.result_hr-g.q).sum(),
                           actual_minus_market_pp=(g.result_hr-g.q).mean()*100,
                           average_p_positive_ev=g.p_positive_ev.mean()*100, average_edge=g.edge.mean(),
                           strabo_brier=((g.result_hr-g.p)**2).mean(),market_brier=((g.result_hr-g.q)**2).mean(),
                           lower_hr_rate=beta.ppf(.05,.5+g.result_hr.sum(),.5+n-g.result_hr.sum())*100,
                           upper_hr_rate=beta.ppf(.95,.5+g.result_hr.sum(),.5+n-g.result_hr.sum())*100,
                           paired_market_brier=((g.loc[g.p.notna(), "result_hr"]-g.loc[g.p.notna(), "q"])**2).mean()))
    return pd.DataFrame(output)


def exposure(rows, stake_column="recommended_units"):
    output = []
    for r in rows:
        stake = r.get(stake_column,0) or 0
        if stake <= 0:
            continue
        for dimension,values in [("Game",[r.get("game_id") or "Unknown"]),("Team",[r.get("team") or "Unknown"]),
                                 ("Signal family",r["signal_families"] or ["Unknown"]),
                                 ("Model family",r["model_families"] or ["Unknown"]),
                                 ("Price bucket",[r["price_bucket"]])]:
            for value in values:
                output.append(dict(dimension=dimension,group=value,allocated_units=stake/len(values),gross_units=stake))
    if not output:
        return pd.DataFrame(columns=["dimension","group","allocated_units","gross_units","share","hhi"])
    frame = pd.DataFrame(output).groupby(["dimension","group"],as_index=False).sum()
    frame["share"] = frame.allocated_units/frame.groupby("dimension").allocated_units.transform("sum")
    frame["hhi"] = frame.share**2
    return frame


def history_export(raw, kind, bankroll, window=20):
    """Export the same stake basis and settled path used by the displayed charts."""
    f = strategy(raw, kind)
    if f.empty:
        return f
    path = timeline(f, bankroll, window)
    f = f.drop(columns=["bankroll_before", "bankroll_after"], errors="ignore")
    path_fields = ["snapshot_id", "bankroll_before", "bankroll_after", "cumulative_profit", "cumulative_expected", "drawdown_percent"]
    if not path.empty:
        f = f.merge(path[path_fields], on="snapshot_id", how="left", validate="one_to_one")
    else:
        for field in path_fields[1:]:
            f[field] = np.nan
    f["history_basis"] = "Recorded wagers" if kind == "actual" else "Forward recommendations (simulated)"
    f["simulated_profit_units"] = f.profit if kind != "actual" else np.nan
    for column in f:
        if f[column].map(lambda value: isinstance(value, (dict, list))).any():
            import json
            from .history import clean
            f[column] = f[column].map(lambda value: json.dumps(clean(value)))
    return f




def portfolio_positions(rows, actual=(), historical=False):
    recorded = {r["player_key"] for r in actual}
    positions = [dict(r, exposure_units=r.get("recommended_units", 0), position_source="Recommended")
                 for r in rows if r["player_key"] not in recorded]
    positions += [dict(r, exposure_units=r["actual_units_bet"], position_source="Recorded")
                  for r in actual if historical or r.get("result", "Pending") == "Pending"]
    return [r for r in positions if r["exposure_units"] > 0]


def portfolio_expected_roi(positions):
    total_stake = 0.
    expected_profit = 0.
    for row in positions:
        stake = float(row["exposure_units"])
        if stake <= 0:
            continue
        probability = row.get("estimated_hr_probability")
        odds = row.get("actual_american_odds") if row["position_source"] == "Recorded" else row.get("american_odds")
        try:
            probability = float(probability)
            if not np.isfinite(probability) or not 0 <= probability <= 1 or not np.isfinite(stake):
                return None
            expected_profit += stake * ev(probability, odds)
        except (TypeError, ValueError):
            return None
        total_stake += stake
    return 100 * expected_profit / total_stake if total_stake else None


def portfolio_roi_coverage(positions):
    modeled = [r for r in positions if portfolio_expected_roi([r]) is not None]
    missing = [r for r in positions if portfolio_expected_roi([r]) is None]
    return dict(roi=portfolio_expected_roi(positions), modeled_roi=portfolio_expected_roi(modeled),
                modeled_count=len(modeled), total_count=len(positions),
                modeled_units=sum(r["exposure_units"] for r in modeled),
                total_units=sum(r["exposure_units"] for r in positions),
                missing_players=[r.get("player", "Unknown player") for r in missing])


def portfolio_settlement_summary(actual):
    rows = [r for r in actual if r.get("actual_units_bet", 0) > 0]
    settled = [r for r in rows if r.get("result") in {"HR", "No HR"}]
    voids = [r for r in rows if r.get("result") == "Void"]
    pending = [r for r in rows if r.get("result") not in {"HR", "No HR", "Void"}]
    profit = 0.
    for row in settled:
        try:
            profit += row["actual_units_bet"] * ev(int(row["result"] == "HR"), row.get("actual_american_odds"))
        except (TypeError, ValueError):
            profit = np.nan
    stake = sum(r["actual_units_bet"] for r in settled)
    return dict(count=len(rows), recorded_units=sum(r["actual_units_bet"] for r in rows),
                pending_count=len(pending), pending_units=sum(r["actual_units_bet"] for r in pending),
                settled_count=len(settled), void_count=len(voids),
                provisional_count=sum(bool(r.get("result_provisional", False)) for r in settled),
                profit=profit if np.isfinite(profit) else None,
                roi=100 * profit / stake if stake and np.isfinite(profit) else None)


def matchup_labels(rows):
    games = {}
    for r in rows:
        gid = str(r.get("game_id") or "Unknown")
        team, opponent = str(r.get("team") or "").upper(), str(r.get("opponent") or "").upper()
        if gid not in games or not games[gid]["pair"]:
            games[gid] = dict(label=f"{team} vs {opponent}" if team and opponent else "Matchup unavailable",
                              pair=tuple(sorted([team, opponent])) if team and opponent else (),
                              start=str(r.get("start_time") or ""))
    pairs = {}
    for gid, game in games.items():
        pairs.setdefault(game["pair"], []).append(gid)
    for pair, gids in pairs.items():
        if len(gids) > 1:
            for number, gid in enumerate(sorted(gids, key=lambda value: (games[value]["start"], value)), 1):
                games[gid]["label"] += f" / G{number}"
    return {gid: game["label"] for gid, game in games.items()}


def exposure_segments(positions, dimension="Game"):
    matchups = matchup_labels(positions)
    rows = []
    for r in positions:
        groups = {"Game": [matchups[str(r.get("game_id") or "Unknown")]],
                  "Team": [r.get("team") or "Unknown"],
                  "Signal family": r["signal_families"] or ["Unknown"],
                  "Model family": r["model_families"] or ["Unknown"],
                  "Price bucket": [r["price_bucket"]]}[dimension]
        for group in groups:
            rows.append(dict(group=group, player=r["player"], player_key=r["player_key"],
                             units=r["exposure_units"]/len(groups), source=r["position_source"],
                             american_odds=r.get("actual_american_odds") if r["position_source"] == "Recorded" else r.get("american_odds"),
                             team=str(r.get("team") or "Unknown").upper()))
    if not rows:
        return pd.DataFrame()
    f = pd.DataFrame(rows).sort_values(["group", "player", "player_key"]).reset_index(drop=True)
    f["end"] = f.groupby("group").units.cumsum()
    f["start"] = f.end-f.units
    f["midpoint"] = (f.start+f.end)/2
    return f


PORTFOLIO_LINES = {
    "realized": "Realized P/L",
    "expected": "Model-expected P/L",
    "flat": "Flat 1u P/L",
    "peak": "P/L high-water mark",
    "drawdown": "Drawdown (units)",
    "residual": "Realized minus expected",
    "baseline": "Break-even",
}


def portfolio_curve(frame):
    """Calendar-day closing curves for one explicit actual/simulated stake basis."""
    settled = graded(frame)
    if settled.empty:
        return pd.DataFrame(columns=["date"]+list(PORTFOLIO_LINES))
    daily = settled.groupby("date", as_index=False).agg(
        profit=("profit", "sum"),
        expected_profit=("expected_profit", lambda values: values.sum(min_count=1) if values.notna().any() else np.nan),
        expected_positions=("expected_profit", lambda values: values.notna().sum()),
        flat_profit=("return_1u", "sum"), bets=("stake", "size"), units=("stake", "sum"))
    has_expected = daily.expected_profit.notna().any()
    daily["date"] = pd.to_datetime(daily.date)
    first = daily.date.min()-pd.Timedelta(days=1)
    daily = daily.set_index("date").reindex(pd.date_range(first, daily.date.max(), freq="D"), fill_value=0)
    daily.index.name = "date"
    daily["realized"] = daily.profit.cumsum()
    if has_expected:
        daily["expected"] = daily.expected_profit.fillna(0).cumsum()
    else:
        daily["expected"] = np.nan
    daily["expected_positions"] = daily.expected_positions.cumsum()
    daily["flat"] = daily.flat_profit.cumsum()
    daily["peak"] = daily.realized.cummax().clip(lower=0)
    daily["drawdown"] = daily.realized-daily.peak
    daily["residual"] = daily.realized-daily.expected
    daily["baseline"] = 0.
    return daily.reset_index()
