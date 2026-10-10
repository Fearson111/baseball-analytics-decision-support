from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from . import charts, config as settings, data, engine, history, metrics, posterior
from .decisions import needs_refresh, unrecorded_decisions
from ..table_display import dataframe, display_name


def table(frame, key=None):
    frame=frame.copy()
    for column in frame:
        if "brier" in str(column).lower() and pd.api.types.is_numeric_dtype(frame[column]):
            frame[column]=frame[column]*100
            frame=frame.rename(columns={column:str(column)+" (x100)"})
    dataframe(frame, hide_index=True, width="stretch", key=key)


def decision_table(rows):
    cols={"player":"Player","sportsbook":"Book","american_odds":"Odds", "break_even_probability":"Break-even %",
          "estimated_hr_probability":"Final HR %","probability_edge_pp":"Edge (pp)","expected_value_per_unit":"EV / 1u",
          "p_positive_ev":"P(EV > 0)","independent_family_count":"Families", "kelly_fractional":"Fractional Kelly %",
          "recommended_units":"Stake (u)","primary_reason":"Reason"}
    f=pd.DataFrame(rows).reindex(columns=list(cols)).rename(columns=cols)
    for c in ("Break-even %","Final HR %","P(EV > 0)","Fractional Kelly %"):
        f[c]=f[c].map(lambda v:f"{v*100:.1f}%" if pd.notna(v) else "")
    f["Odds"]=f["Odds"].map(lambda v:f"{v:+.0f}" if pd.notna(v) else "")
    for c in ("Stake (u)","EV / 1u"):
        f[c]=f[c].map(lambda v:f"{v:.2f}u" if pd.notna(v) else "")
    return f


def settlement_caption(actual):
    summary = metrics.portfolio_settlement_summary(actual)
    if not summary["count"]:
        return
    parts = [f"{summary['recorded_units']:.2f}u recorded"]
    if summary["pending_count"]:
        count = summary["pending_count"]
        parts.append(f"{count} unsettled wager{'s' if count != 1 else ''} ({summary['pending_units']:.2f}u)")
    elif not summary["provisional_count"]:
        parts.append("All wagers settled")
    if summary["settled_count"]:
        label = "Settled P/L" if summary["pending_count"] else "Net P/L"
        if summary["provisional_count"]:
            label = "P/L including live HR"
        profit = summary["profit"]
        if profit is not None:
            profit = Decimal(str(profit)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        parts.append(f"{label}: {profit:+.2f}u" if profit is not None else f"{label}: unavailable")
        if summary["roi"] is not None:
            label = "ROI on settled wagers" if summary["pending_count"] else "Realized ROI"
            if summary["provisional_count"]:
                label = "ROI on resolved wagers (incl. live HR)"
            roi = Decimal(str(summary["roi"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            parts.append(f"{label}: {roi:+.2f}%")
    if summary["void_count"]:
        parts.append(f"{summary['void_count']} void (excluded from ROI)")
    if summary["provisional_count"]:
        parts.append(f"{summary['provisional_count']} live HR awaiting final confirmation")
    st.caption(" | ".join(parts))


@st.fragment(run_every="30s")
def live_result_monitor(root, day):
    if day != date.today().isoformat():
        return
    from .results import scan_day
    try:
        report = scan_day(root, day, include_live=True, recorded_only=True, min_interval_seconds=30)
    except Exception:
        st.caption("Live results check unavailable; showing the last saved results.")
        return
    revision_key = "financial_results_revision_" + str(root) + "_" + day
    previous = st.session_state.get(revision_key)
    revision = report.get("result_revision")
    st.session_state[revision_key] = revision
    if report["newly_graded"] or report["corrected"] or report["finalized"] or (previous is not None and previous != revision):
        st.rerun()
    if report["tracked_players"]:
        stamp = datetime.fromisoformat(report["checked_at"]).astimezone(ZoneInfo("America/Denver"))
        st.caption(f"MLB results checked {stamp:%I:%M:%S %p %Z}. "
                   + ("Some results unavailable; saved results retained." if report["errors"] else "Live HR credits are provisional until final."))


@st.fragment(run_every="30s")
def current_exposure_view(root, day, config, dimension):
    actual = history.read(root, actual=True)
    existing = actual[actual.date.eq(day)].to_dict("records") if not actual.empty else []
    recorded_units = sum(r["actual_units_bet"] for r in existing)
    with st.container(key="portfolio_budget_metrics"):
        used, remaining, roi = st.columns(3)
        used.metric("Recorded stake", f"{recorded_units:.2f}u")
        remaining.metric("Remaining budget", f"{max(0., config.max_daily-recorded_units):.2f}u")
        with roi:
            expected_roi_metric(metrics.portfolio_roi_coverage(metrics.portfolio_positions([], existing)))
    exposure_view([], existing, config=config, dimension=dimension, show_roi=False)


def expected_roi_metric(coverage):
    expected_roi = coverage["modeled_roi"]
    label = "Expected ROI (modeled)" if coverage["missing_players"] else "Expected ROI"
    value = f"{expected_roi:+.2f}%" if expected_roi is not None else "Not available"
    st.metric(label, value, help="Model-expected profit divided by the same wagers' allocated stake, using their recorded odds including boosts. When coverage is partial, only modeled wagers enter this estimate and its stake denominator. This is not realized ROI.")


def exposure_view(rows, actual=(), *, historical=False, config=None, dimension="Game", show_roi=True):
    config = config or settings.Config()
    # Live portfolio exposure belongs only to explicitly recorded wagers.
    positions = metrics.portfolio_positions(rows if historical else [], actual, historical)
    if not positions:
        settlement_caption(actual)
        st.info("No active exposure on this slate." if not historical else "No allocated positions on this date.")
        return
    coverage = metrics.portfolio_roi_coverage(positions)
    labels = metrics.matchup_labels(positions)
    if len(positions) == 1:
        row = positions[0]
        if show_roi:
            left, right = st.columns([3, 1])
        else:
            left = st.container()
        left.markdown("**" + display_name(row["player"]) + "**")
        left.write(labels[str(row.get("game_id") or "Unknown")])
        odds = row.get("actual_american_odds") if row["position_source"] == "Recorded" else row.get("american_odds")
        quote = f"{odds:+.0f}" if odds is not None else "Price unavailable"
        left.caption(f"{row.get('sportsbook') or 'Book not recorded'} · {quote} · {row['position_source']}")
        if show_roi:
            with right.container(key="portfolio_roi_metric"):
                expected_roi_metric(coverage)
        stake = row["exposure_units"]
        st.progress(min(stake/config.max_game, 1.),
                    text=f"Game exposure: {stake:.2f}u / {config.max_game:.2f}u configured cap")
        if stake > config.max_game:
            st.warning("This recorded allocation exceeds the current game cap; the actual stake is preserved.")
    else:
        f = metrics.exposure(positions, "exposure_units")
        subset = f[f.dimension.eq(dimension)].copy()
        total = subset.allocated_units.sum()
        columns = st.columns(4 if show_roi else 3)
        a, b, c = columns[:3]
        a.markdown(f"**{len(positions)} positions · {total:.2f}u**")
        b.markdown(f"**{subset.group.nunique()} {dimension.lower()} groups**")
        c.markdown(f"**HHI {subset.hhi.sum():.2f}**",
                   help="Sum of squared stake shares for the selected grouping. 1.00 means all exposure is in one group.")
        if show_roi:
            with columns[3].container(key="portfolio_roi_metric"):
                expected_roi_metric(coverage)
    settlement_caption(actual)
    segments = metrics.exposure_segments(positions, dimension)
    charts.player_exposure(segments)
    with st.expander("Exposure details"):
        if coverage["missing_players"]:
            names = ", ".join(display_name(name) for name in coverage["missing_players"])
            st.caption(f"Expected-ROI coverage: {coverage['modeled_count']} of {coverage['total_count']} positions "
                       f"({coverage['modeled_units']:.2f}u of {coverage['total_units']:.2f}u). "
                       f"No saved probability or valid odds for: {names}. Realized P/L does not need a model probability.")
        table(segments[["group", "player", "team", "units", "source"]]
              .drop(columns=["team"] if dimension == "Team" else [])
              .rename(columns={"group": dimension, "player": "Player", "team": "Team",
                               "units": "Allocated units", "source": "Position"}))
        st.caption("Family allocations split shared stakes; risk caps count the full stake in each related family.")


def portfolio_performance(forward, actual):
    st.subheader("Portfolio P/L Over Time")
    basis = st.radio("Portfolio history basis", ["Recorded wagers", "Forward recommendations (simulated)"],
                     horizontal=True, key="portfolio_curve_basis")
    raw = actual if basis == "Recorded wagers" else forward
    f = metrics.strategy(raw, "actual" if basis == "Recorded wagers" else "sized")
    selected = st.multiselect("Visible lines", list(metrics.PORTFOLIO_LINES.values()),
                             default=["Realized P/L", "Model-expected P/L", "Break-even"],
                             key="portfolio_curve_lines")
    st.caption("All lines use units and calendar-day totals. Pending and void wagers are excluded. Live HR credits are included provisionally and reconciled against final results.")
    curve = metrics.portfolio_curve(f)
    if curve.empty:
        st.info("The P/L chart begins after the first financial wager settles. No historical signal profits or placeholder results are added.")
    else:
        charts.portfolio_history(curve, {key: label for key, label in metrics.PORTFOLIO_LINES.items() if label in selected})
        a, b, c = st.columns(3)
        a.metric("Realized P/L", f"{curve.realized.iloc[-1]:+.2f}u")
        expected_available = "expected_positions" not in curve or curve.expected_positions.iloc[-1] > 0
        b.metric("Model-expected P/L", f"{curve.expected.iloc[-1]:+.2f}u" if expected_available and pd.notna(curve.expected.iloc[-1]) else "Not available")
        c.metric("Current drawdown", f"{curve.drawdown.iloc[-1]:.2f}u")
        if expected_available and "expected_positions" in curve and curve.expected_positions.iloc[-1] < curve.bets.sum():
            st.caption(f"Expected P/L covers {int(curve.expected_positions.iloc[-1])} of {int(curve.bets.sum())} settled wagers; the line stays flat where a recorded wager has no saved model probability.")
        st.download_button("Download Portfolio Curve CSV", curve.to_csv(index=False).encode("utf-8-sig"),
                           "portfolio_curve_" + ("recorded" if basis == "Recorded wagers" else "simulated") + ".csv",
                           "text/csv")
    with st.expander("Reference line definitions"):
        st.markdown(
            "- **Realized P/L:** Actual outcomes at the selected basis's stakes and prices.\n"
            "- **Model-expected P/L:** Frozen estimated EV multiplied by those stakes, for the same settled positions.\n"
            "- **Flat 1u P/L:** The same positions and prices, but with every stake set to 1u. This compares sizing, not a different player-selection rule.\n"
            "- **P/L high-water mark:** Highest day-closing cumulative profit reached, including the initial zero.\n"
            "- **Drawdown (units):** Current cumulative profit minus that peak; zero or negative.\n"
            "- **Realized minus expected:** The gap between actual profit and modeled expectation. This is not a confidence interval or a pure luck measurement.\n"
            "- **Break-even:** The zero-profit reference."
        )


def inspector(rows, config, root):
    st.subheader("Player Decision Inspector")
    if not rows:
        return
    names=[r["player"] for r in rows]
    selected=st.selectbox("Player",names, format_func=display_name)
    row=rows[names.index(selected)]
    st.info(row["explanation"])
    charts.price_probability(row)
    a,b,c,d=st.columns(4)
    a.metric("Price bucket",row["price_bucket"])
    b.metric("Credible interval",f"{row['posterior_lower']:.1%} to {row['posterior_upper']:.1%}")
    c.metric("Effective observations",f"{row['effective_sample_size']:.1f}")
    d.metric("Conservative EV",f"{row['conservative_ev']:+.2f}u")
    st.caption(f"{config.credible_mass:.0%} uncertainty interval. Method: {row['probability_method']}. "
               f"Quote source: {row.get('odds_source','unknown')}; observed {row.get('odds_observed','unknown')}. "
               "Observed aggregator time is not the sportsbook's last-change time.")
    st.markdown("**Signal families:** " + ", ".join(row["signal_families"]))
    st.caption("Distinct families are overlapping factors, not statistically independent votes. Price-conditioned evidence also matches base-model probability within 5 percentage points and counts each player-day once.")
    evidence=pd.DataFrame(row["signal_evidence"])
    charts.shrinkage(evidence[evidence.scope.eq("Current price bucket")])
    pretty=evidence.copy()
    for col in ("raw_hr_rate","shrunk_hr_rate","lower","upper"):
        pretty[col]=pretty[col]*100
    table(pretty.rename(columns={"raw_hr_rate":"Raw HR %","shrunk_hr_rate":"Shrunk HR %","lower":"Lower %","upper":"Upper %","gap_pp":"Gap vs today's price (pp)"}))
    with st.expander("Probability and sizing audit"):
        fields=["base_model_probability","prior_probability","posterior_mean","posterior_median","posterior_std",
                "effective_sample_size","shrinkage_amount","historical_bets","historical_hr","peer_bets",
                "kelly_full","kelly_fraction_used","kelly_fractional","recommended_units","stake_caps_applied",
                "model_version","config_version","training_through"]
        probabilities={"base_model_probability","prior_probability","posterior_mean","posterior_median","posterior_std","kelly_full","kelly_fraction_used","kelly_fractional"}
        audit=[]
        for field in fields:
            value=row.get(field)
            text="" if value is None else f"{value:.1%}" if field in probabilities else f"{value*100:+.1f} pp" if field=="shrinkage_amount" else str(value)
            audit.append({"Field":field.replace("_"," ").title(),"Value":text})
        table(pd.DataFrame(audit))


@st.dialog("Record Bet", width="large")
def record_bet_dialog(root, rows, selected_day):
    from .bet_log import player_options, log_bet
    from ..daily_hub.markets import key, number
    day = st.date_input("Bet date", value=date.fromisoformat(selected_day), key="personal_bet_day").isoformat()
    options = player_options(root, day)
    labels = {}
    for r in options:
        matchup = f" · {r.get('team') or '?'} vs {r.get('opponent') or '?'}" if r.get("game_id", "").isdigit() else ""
        game = f" · G{r['game_number']}" if str(r.get("game_number") or "") not in {"", "1"} else ""
        label = display_name(r["player"]) + matchup + game
        if label in labels:
            label += " · " + str(r.get("start_time") or r.get("game_id"))
        labels[label] = r
    selected = st.selectbox("Player", list(labels), index=None, accept_new_options=True,
                            placeholder="Choose a player or type a name", key="personal_bet_player")
    context = labels.get(selected, {})
    if selected and not context:
        matches = [r for r in options if key(r["player"]) == key(selected)]
        if len(matches) == 1:
            context = matches[0]
    player = context.get("player") or selected or ""
    actual = history.read(root, actual=True)
    found = actual[actual.date.eq(day) & actual.player_key.eq(key(player))] if not actual.empty else actual
    existing = found.iloc[0].to_dict() if not found.empty else None
    if existing:
        st.caption("This bet is already saved. Update its details below.")
    initial_units = float(existing["actual_units_bet"]) if existing else 1.
    initial_odds = float(existing["actual_american_odds"]) if existing else number(context.get("american_odds")) or 100.
    initial_book = (existing.get("actual_sportsbook") or existing.get("sportsbook") or "") if existing else context.get("sportsbook") or ""
    with st.form("personal_bet_" + day + key(player)):
        left, right = st.columns(2)
        units = left.number_input("Stake (units)", min_value=.01, value=initial_units, step=.25, format="%.2f")
        odds = right.number_input("American odds", value=initial_odds, step=5., format="%.0f")
        book = st.text_input("Sportsbook", value=initial_book)
        if st.form_submit_button("Update Bet" if existing else "Save Bet", icon=":material/check:", width="stretch"):
            try:
                if not player:
                    raise ValueError("Choose or enter a player.")
                log_bet(root, day, player, units, odds, book, context=context, replace=bool(existing))
                st.session_state["financial_record_notice"] = f"{'Updated' if existing else 'Saved'} {display_name(player)}: {units:.2f}u at {odds:+.0f}" + (f" on {book}." if book else ".")
                st.session_state["financial_rebuild"] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def record_bet_control(root, rows, selected_day):
    if st.button("Record Bet", icon=":material/add:", key="financial_open_record"):
        record_bet_dialog(root, rows, selected_day)


def history_charts(records, config):
    st.subheader("Financial Betting History")
    choice=st.radio("History basis",["Forward recommendations (simulated)","Recorded wagers"],horizontal=True)
    raw=records[1] if choice=="Recorded wagers" else records[0]
    if choice=="Recorded wagers" and not raw.empty and "entry_method" in raw:
        later=int(raw.entry_method.isin(["Logged later", "Personal bet log"]).sum())
        if later:
            st.caption(f"Includes {later} manually logged wagers. Actual bankroll includes them; the model\'s forward-validation record is separate.")
    f=metrics.strategy(raw,"actual" if choice=="Recorded wagers" else "sized")
    st.caption("Only separately captured financial decisions appear here. Pending and void observations are excluded from settled ROI and calibration. Recommendations are simulated until you explicitly record a wager.")
    window=st.selectbox("Rolling ROI window (settled bets)",[20,50,100])
    summary=metrics.summary(f,config.starting_bankroll,window)
    for cols in [[("Bets","bets"),("HR","hr"),("Units risked","units_risked")],
                 [("Profit / loss","profit"),("ROI %","roi"),("Max drawdown %","max_drawdown")]]:
        for slot,(label,field) in zip(st.columns(3),cols):
            value=summary.get(field)
            slot.metric(label,"Not available" if value is None or pd.isna(value) else str(value) if field in {"bets","hr"} else f"{value:.2f}")
    with st.expander("All financial summary metrics"):
        table(pd.DataFrame([{"Metric":k.replace("_"," ").title()+(" x100" if "brier" in k else ""), "Value":None if v is None or pd.isna(v) else f"{v*100 if 'brier' in k else v:.2f}"} for k,v in summary.items()]))
        st.caption("Sharpe-like and Sortino-like values use unannualized per-bet returns, not institutional risk ratios. Calmar-like uses total return over maximum drawdown for this sample, not an annualized return. Undefined ratios are left blank.")
    t=metrics.timeline(f,config.starting_bankroll,window)
    if t.empty:
        st.info("No settled observations for this financial strategy yet. Curves begin after outcomes are available.")
    else:
        charts.lines(t,"bet",{"cumulative_profit":"Realized","cumulative_expected":"Expected"},"Equity: realized vs expected","Realized profit uses settled results and stakes. Expected profit uses the probability frozen with each decision. Their difference is the P&L residual.")
        a,b=st.columns(2)
        with a:
            charts.lines(t,"bet",{"drawdown_percent":"Drawdown"},"Drawdown","Distance below the running bankroll peak, including the starting bankroll. Zero means a new or recovered peak.","Drawdown (%)")
        with b:
            charts.lines(t,"bet",{"rolling_roi":"Rolling ROI"},"Rolling ROI",f"Profit divided by units risked across exactly {window} settled bets. Values remain blank until the window is full.","ROI (%)")
        with a:
            charts.lines(t,"bet",{"actual_hr":"Actual HR","expected_hr":"Strabo expected HR","market_expected_hr":"Market expected HR"},"Actual vs expected home runs","Each settled player wager contributes one binary result. Expected HR is the sum of frozen probabilities, not weighted by stake.","Cumulative HR")
        with b:
            charts.lines(t,"bet",{"hr_residual":"Actual minus Strabo","market_residual":"Actual minus market"},"Probability residuals","Positive values mean more home runs than predicted. Persistent deviation can reflect selection bias or miscalibration as well as outcome variance.","Cumulative HR residual")
        charts.lines(t,"bet",{"pnl_residual":"Realized minus expected"},"Return residual","This isolates the difference between expected and realized profit; it is not a statistical significance test.")
        daily=t.groupby("date",as_index=False).agg(total_units=("stake","sum"),average_stake=("stake","mean"),maximum_stake=("stake","max"),positions=("stake","size"),opening_bankroll=("bankroll_before","first"))
        daily["bankroll_fraction_at_risk"]=daily.total_units/daily.opening_bankroll*100
        charts.lines(daily,"date",{"total_units":"Daily units","average_stake":"Average stake","maximum_stake":"Maximum stake"},"Stake and exposure history","Settled exposure by date. The table also reports positions and percentage of opening bankroll at risk.",xlabel="Date")
        table(daily)
    if not raw.empty:
        export=metrics.history_export(raw,"actual" if choice=="Recorded wagers" else "sized",config.starting_bankroll,window)
        st.download_button("Download Financial History CSV",export.to_csv(index=False).encode("utf-8-sig"),"financial_history.csv","text/csv")
        table(export.reindex(columns=["date","player","decision","odds","stake","result","result_provisional","profit","bankroll_after","model_version"]))
    return f


def diagnostics(f, records, config):
    charts.reliability(metrics.calibration(f))
    g=metrics.graded(f)
    if not g.empty:
        cloud=alt.Chart(g).mark_circle(opacity=.5).encode(x=alt.X("ev:Q",title="Predicted EV per 1u"),
            y=alt.Y("return_1u:Q",title="Realized profit per 1u"),color=alt.Color("result:N",scale=alt.Scale(range=charts.COLORS)),
            tooltip=["player","date","odds",alt.Tooltip("ev",format=".2f"),alt.Tooltip("return_1u",format=".2f")])
        charts.show(cloud,"EV vs realized return","Individual HR returns are very noisy. The bucket tables below are more useful as the sample grows.")
        g["confidence_bucket"]=pd.cut(g.p_positive_ev,[0,.5,.6,.7,.8,.9,.95,1.00001],include_lowest=True).astype(str)
        g["ev_bucket"]=pd.cut(g.ev,[-np.inf,0,.1,.25,.5,1,np.inf]).astype(str)
        g["family_count_bucket"]=g.independent_family_count.map(lambda n:"4+" if n>=4 else str(n))
        sections=[("Posterior confidence",g,"confidence_bucket"),("Price bucket",g,"price_bucket"),
                  ("Signal family",g.explode("signal_families"),"signal_families"),
                  ("Family diversity",g,"family_count_bucket"),("Expected value",g,"ev_bucket")]
        for title,frame,column in sections:
            with st.expander(title,expanded=title=="Posterior confidence"):
                result=metrics.performance(frame,column)
                charts.bars(result,title+" performance","ROI is stake-weighted. Counts are settled player wagers. Family groups overlap and must not be added together.")
                table(result)
    st.subheader("Strategy Comparison")
    st.caption("All three simulated strategies use the same first pregame player-day cohort. This is a forward comparison, not a mined-rule backtest. No strategy inherits old raw-signal profits.")
    rows=[]
    for name,kind in [("Raw signals / flat 1u","raw"),("Financial BET / flat 1u","filtered"),("Financial BET / sized","sized")]:
        summary=metrics.summary(metrics.strategy(records[0],kind),config.starting_bankroll)
        rows.append({"strategy":name,**summary})
    table(pd.DataFrame(rows).reindex(columns=["strategy","bets","units_risked","profit","roi","max_drawdown","hit_rate","expected_profit","return_volatility"]))


def evidence_view(training, model, config):
    st.subheader("Historical Evidence")
    st.caption("Retrospective raw-signal research, deduplicated to player-days and restricted to dates before this slate. Mined labels may have been chosen with hindsight; even chronological validation here is not proof of prospective profitability.")
    if training.empty:
        st.info("No usable prior player-day evidence is available.")
        return
    dimension=st.selectbox("Research breakdown",["Signal","Signal family","Price bucket","Month"])
    research=training.copy()
    research["p"]=research.base_model_probability
    research["q"]=research.break_even_probability
    research["stake"]=1.
    from .pricing import ev
    research["profit"]=[ev(y,o) for y,o in zip(research.result_hr,research.american_odds)]
    research["result"]=research.result_hr.map({1:"HR",0:"No HR"})
    research["edge"]=(research.p-research.q)*100
    research["p_positive_ev"]=np.nan
    research["month"]=research.date.str[:7]
    col={"Signal":"signal_labels","Signal family":"signal_families","Price bucket":"price_bucket","Month":"month"}[dimension]
    if dimension in {"Signal","Signal family"}:
        research=research.explode(col)
    summary=metrics.performance(research,col)
    summary["base_probability_coverage_note"]="Expected HR and base Brier use only rows with a saved base probability"
    table(summary)
    st.caption(f"{len(training)} player-days; {training.quote_conflict.sum()} with conflicting source prices use the shortest observed quote. "
               f"Base probability coverage: {training.base_model_probability.notna().mean():.1%}. "
               "Family/signal tables overlap. Empirical probabilities and ROI are evidence, never a direct BET trigger.")
    if dimension=="Signal":
        points=[]
        for label,g in research.groupby(col):
            n,k=len(g),int(g.result_hr.sum())
            post=posterior.beta_summary(g.q.mean(),n,k,g.q.mean(),config,min(n,2*g.date.nunique()))
            points.append(dict(signal=label,bets=n,raw_hr_rate=k/n,shrunk_hr_rate=post["posterior_mean"]))
        charts.shrinkage(pd.DataFrame(points))
    st.subheader("Market-Anchored Meta-Model")
    st.caption("Ridge logistic regression keeps market log-odds as a fixed offset. Chronological validation trains only on dates preceding each evaluation block. The Beta model remains the default; the meta-model can be enabled only after its minimum evaluation sample and market-Brier gate pass.")
    model_metrics=[]
    for field in ("status","train_bets","trained_through","oos_bets","market_brier","strabo_brier","gate_passed","version"):
        value=model.get(field)
        model_metrics.append({"Metric":field.replace("_"," ").title()+(" (x100)" if "brier" in field else ""),
                              "Value":"" if value is None else f"{value*100:.1f}" if "brier" in field else str(value)})
    table(pd.DataFrame(model_metrics))
    st.caption("Brier scores are displayed x100 for readability; lower is better. The downloaded model keeps full precision.")
    if model.get("coefficients"):
        table(pd.DataFrame({"Feature":model["features"],"Coefficient":model["coefficients"]}))
        st.download_button("Download Meta-Model JSON",json.dumps(history.clean(model),indent=2),"financial_meta_model.json","application/json")


def config_view(root, config, model):
    st.caption("Settings affect future financial decisions only, not upstream models or frozen historical decisions. Bankroll and caps are in your chosen unit size; the initial 100u is a research default, not your account balance.")
    with st.form("financial_config"):
        a,b,c=st.columns(3)
        changes={}
        fields=[("Starting bankroll (u)","starting_bankroll"),("Maximum daily exposure (u)","max_daily"),
                ("Maximum single stake (u)","max_stake"),("Maximum game exposure (u)","max_game"),
                ("Maximum team exposure (u)","max_team"),("Maximum family exposure (u)","max_family"),
                ("Maximum model exposure (u)","max_model"),("Minimum matched player-days","min_sample"),
                ("Prior strength","prior_strength"),("Effective sample cap","effective_sample_cap"),
                ("Minimum edge (pp)","min_edge_pp"),("Maximum quote age (minutes)","max_quote_age_minutes"),("Ridge strength","ridge"),
                ("Minimum training rows","min_train"),("Minimum validation rows","min_oos")]
        for i,(label,field) in enumerate(fields):
            value=getattr(config,field)
            changes[field]=(a,b,c)[i%3].number_input(label,min_value=1 if isinstance(value,int) else .01,value=value)
        for i,(label,field) in enumerate([("Minimum P(EV > 0)","min_p_positive_ev"),("Credible interval mass","credible_mass"),("Maximum interval width","max_interval_width"),("Kelly fraction","kelly_fraction")]):
            changes[field]=(a,b,c)[i%3].slider(label,.01,.99,float(getattr(config,field)),.01)
        boundaries=st.text_input("Positive American price boundaries",", ".join(str(x) for x in config.price_breaks))
        changes["require_confirmed"]=st.checkbox("Require confirmed starter for BET",value=config.require_confirmed)
        changes["use_meta"]=st.checkbox("Use market-offset meta-model when validation gate passes",value=config.use_meta)
        if st.form_submit_button("Save Financial Settings"):
            try:
                changes["price_breaks"]=[float(x.strip()) for x in boundaries.split(",")]
                new=settings.Config(**{**asdict(config),**changes}).validate()
                settings.save(root,new)
                st.success("Saved. Rebuild financial decisions to apply these settings to the current slate.")
            except ValueError as exc:
                st.error(str(exc))


def render(root: Path, out: Path):
    st.subheader("Financial Decision System")
    st.caption("PRICE  /  EVIDENCE  /  UNCERTAINTY  /  PORTFOLIO")
    config=settings.load(root)
    folder=out/"FINANCIAL_SYSTEM"
    a,b=st.columns(2)
    rebuild=a.button("Rebuild Financial Decisions",icon=":material/refresh:", width="stretch") or st.session_state.pop("financial_rebuild",False)
    fetch_results=b.button("Fetch & Grade Portfolio Results",icon=":material/cloud_download:", width="stretch",
                           help=f"Check MLB live home runs and final results for financial positions on {out.name}. Does not run prediction models.")
    if fetch_results:
        from .results import scan_day
        try:
            with st.spinner(f"Checking final MLB box scores for the {out.name} financial portfolio..."):
                report=scan_day(root,out.name,include_live=True)
            st.success(f"{out.name}: {report['newly_graded']} newly graded, {report['corrected']} corrected, "
                       f"{report['unchanged']} unchanged; {report['pending_players']} still pending. "
                       f"Checked {report['live_games']} live and {report['final_games']} final boxes.")
            if not report["tracked_players"]:
                st.info("No captured financial positions exist for this date.")
            for error in report["errors"]:
                st.warning(error)
        except Exception as exc:
            st.error(f"Portfolio result fetch could not complete: {exc}")
    live_result_monitor(root, out.name)
    if (folder/"decisions.json").exists() and out.name==date.today().isoformat():
        actual = history.read(root, actual=True)
        existing = actual[actual.date.eq(out.name)].to_dict("records") if not actual.empty else []
        cached=json.loads((folder/"decisions.json").read_text())
        frozen=settings.Config(**json.loads((folder/"config.json").read_text()))
        rebuild=rebuild or needs_refresh(cached,frozen) or engine.wagers_changed(folder, existing)
    if rebuild or not (folder/"decisions.json").exists():
        with st.spinner("Combining price, evidence and portfolio risk..."):
            from ..daily_hub.runner import read_json, snapshot_lock
            persist=out.name==date.today().isoformat() and read_json(out.parent/"status.json").get("mode")!="saved"
            with snapshot_lock():
                engine.build(root,out,persist=persist)
    rows=json.loads((folder/"decisions.json").read_text())
    model=json.loads((folder/"model.json").read_text())
    stored=settings.Config(**json.loads((folder/"config.json").read_text()))
    if config.signature!=stored.signature:
        st.warning("Settings changed since this snapshot. Rebuild to apply them; displayed decisions retain their stored configuration.")
    # All displays for a frozen snapshot use its own interval/bankroll settings.
    actual=history.read(root,actual=True)
    forward=history.read(root)
    existing=actual[actual.date.eq(out.name)].to_dict("records") if not actual.empty else []
    live_wins = actual[actual.result_provisional.eq(True)] if not actual.empty and "result_provisional" in actual else pd.DataFrame()
    if not live_wins.empty:
        names = ", ".join(display_name(name) for name in live_wins.player)
        st.caption(f"Provisional live HR: {names}. Financial totals include these credits; official scoring corrections can reverse them.")
    visible_rows=unrecorded_decisions(rows, existing)
    bets=[r for r in visible_rows if r["decision"]=="BET"]
    recorded_units=sum(r["actual_units_bet"] for r in existing)
    remaining_units=max(0., stored.max_daily-recorded_units)
    for col,label,value in zip(st.columns(4),["BET candidates","Recommended exposure","Expected profit","Average edge"],
                              [str(len(bets)),f"{sum(r['recommended_units'] for r in bets):.2f}u",
                               f"{sum(r['recommended_units']*r['expected_value_per_unit'] for r in bets):+.2f}u",
                               f"{np.mean([r['probability_edge_pp'] for r in bets]):+.1f} pp" if bets else "No BET"]):
        col.metric(label,value)
    st.caption(f"Daily budget: {recorded_units:.2f}u recorded / {stored.max_daily:.2f}u cap. "
               f"{remaining_units:.2f}u available for new recommendations.")
    record_bet_control(root, rows, out.name)
    notice=st.session_state.pop("financial_record_notice", None)
    if notice:
        st.success(notice)
    st.caption("Experimental decision support. Probability intervals and P(EV > 0) depend on model assumptions; retrospective signal mining can exaggerate evidence. Distinct families are not independent confirmations. No wagers are placed automatically.")
    tabs=st.tabs(["Decisions","Evidence","Portfolio","History & Calibration","Settings"])
    with tabs[0]:
        for decision in ("BET","MARGINAL / WATCH","PASS"):
            subset=[r for r in visible_rows if r["decision"]==decision]
            with st.expander(f"{decision} · {len(subset)}",expanded=decision!="PASS"):
                if subset:
                    table(decision_table(subset))
                else:
                    st.caption("No candidates in this decision group.")
        if visible_rows:
            st.download_button("Download Financial Decisions CSV",engine.decision_export(visible_rows).to_csv(index=False).encode("utf-8"),f"financial_decisions_{out.name}.csv","text/csv")
        inspector(visible_rows,stored,root)
    with tabs[1]:
        from ..daily_hub.history import straight_history
        training=data.history_players(straight_history(root),out.name,stored)
        evidence_view(training,model,stored)
    with tabs[2]:
        st.subheader("Today's Portfolio Concentration" if out.name == date.today().isoformat()
                     else f"Portfolio Concentration · {out.name}")
        view_control, group_control = st.columns(2)
        basis=view_control.selectbox("Portfolio view",["Current slate (recorded wagers)","Frozen recommendations","Recorded wagers"])
        dimension=group_control.selectbox("Group by",["Game","Team","Signal family","Model family","Price bucket"],
                                          key="financial_exposure_dimension")
        if basis=="Current slate (recorded wagers)":
            current_exposure_view(root,out.name,stored,dimension)
        else:
            positions=forward if basis=="Frozen recommendations" else actual
            if positions.empty:
                st.info("No captured positions for this portfolio basis yet.")
            else:
                day=st.selectbox("Exposure date",sorted(positions.date.unique(),reverse=True))
                selected_positions=positions[positions.date.eq(day)].to_dict("records")
                exposure_view(selected_positions if basis=="Frozen recommendations" else [],selected_positions if basis=="Recorded wagers" else [],historical=True,config=stored,dimension=dimension)
        if existing:
            with st.expander(f"Recorded wagers ({len(existing)})"):
                records=pd.DataFrame(existing).reindex(columns=["player","actual_units_bet","actual_american_odds","actual_sportsbook","entry_method","placed_at","recorded","result","result_provisional"])
                records["actual_units_bet"]=records.actual_units_bet.map(lambda value:f"{value:.2f}u")
                records["actual_american_odds"]=records.actual_american_odds.map(lambda value:f"{value:+.0f}")
                table(records.rename(columns={"player":"Player","actual_units_bet":"Stake",
                                              "actual_american_odds":"Odds","actual_sportsbook":"Book",
                                              "entry_method":"Entry","placed_at":"Placed at","recorded":"Logged at","result":"Result"}))
                selected=st.selectbox("Recorded wager",[r["player"] for r in existing], format_func=display_name)
                if st.button("Remove Mistaken Record"):
                    try:
                        r=next(r for r in existing if r["player"]==selected)
                        history.remove_record(root,history.identity(r))
                        st.session_state["financial_rebuild"]=True
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        portfolio_performance(forward,actual)
    with tabs[3]:
        f=history_charts((forward,actual),stored)
        diagnostics(f,(forward,actual),stored)
    with tabs[4]:
        config_view(root,config,model)
        st.markdown("**Method references:** [Beta posterior calculations](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.beta.html) · [Calibration and Brier scores](https://scikit-learn.org/stable/modules/calibration.html)")
