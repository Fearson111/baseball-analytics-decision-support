from __future__ import annotations

from pathlib import Path
import pandas as pd
from ..table_display import dataframe as display_dataframe

from . import ledger
from ..retired_signals import without_retired_signals


def straight_history(root: Path) -> pd.DataFrame:
    from ..profit_lens_app import build_history_frame, build_regression_misprice_history_frame, STRAIGHT_LENS_SIGNAL_LABELS
    from ..edge_buckets import build_edge_bucket_history_rows
    from ..sequence_edge import historical_signal_rows
    lenses = build_history_frame(root).rename(columns={"lens": "signal"})
    if "signal" in lenses:
        lenses["signal"] = lenses["signal"].map(lambda s: STRAIGHT_LENS_SIGNAL_LABELS.get(s, s))
    regression = build_regression_misprice_history_frame(root).rename(columns={"zone": "signal"})
    frames = [lenses, regression, pd.DataFrame(build_edge_bucket_history_rows()), historical_signal_rows(root)]
    legacy = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
    path = root / "DAILY_BASEBALL" / "ledger.sqlite3"
    boundary = ledger.first_day(path)
    if boundary and not legacy.empty:
        legacy = legacy[legacy["game_date"].astype(str).lt(boundary)]
    fresh = ledger.history(path)
    return without_retired_signals(pd.concat([f for f in [legacy, fresh] if not f.empty], ignore_index=True)) if not legacy.empty or not fresh.empty else pd.DataFrame()


def stats(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    output = {}
    for signal, group in frame.groupby("signal", sort=False):
        results = group["result"].fillna("").astype(str).str.upper()
        graded = group[results.isin(["HR", "NO HR", "NO_HR"])].copy()
        hits = int(graded["result"].astype(str).str.upper().eq("HR").sum())
        profit = float(pd.to_numeric(graded["profit_1u"], errors="coerce").fillna(0).sum())
        bets = len(graded)
        roi = profit / bets * 100 if bets else 0
        output[str(signal)] = f"{bets} bets, {hits} HR, {profit:+.2f}u, {roi:+.2f}% ROI"
    return output


def signal_history_table(frame: pd.DataFrame) -> pd.DataFrame:
    view = frame.sort_values(["game_date", "player", "signal"], kind="stable").copy()
    settled = view["result"].astype(str).str.upper().isin(["HR", "NO HR", "NO_HR"])
    view["profit_1u"] = pd.to_numeric(view["profit_1u"], errors="coerce").where(settled, 0).fillna(0)
    view["running_profit_1u"] = view["profit_1u"].cumsum()
    # Reverse the entire accumulation order, including same-day rows, not just dates.
    return view.iloc[::-1].reset_index(drop=True)


def render_history(root: Path):
    import streamlit as st
    st.subheader("Signal History")
    frame = straight_history(root)
    if frame.empty:
        st.info("No graded signal history available.")
        return
    selected = st.selectbox("Signal", ["All"] + sorted(frame["signal"].dropna().unique()))
    view = frame if selected == "All" else frame[frame["signal"].eq(selected)]
    view = signal_history_table(view)
    graded = view[view["result"].astype(str).str.upper().isin(["HR", "NO HR", "NO_HR"])]
    chart = graded.groupby("game_date")["profit_1u"].sum().cumsum()
    st.line_chart(chart.rename("Profit/Loss"), height=260)
    a, b, c, d = st.columns(4)
    profit = graded["profit_1u"].sum()
    a.metric("Bets", len(graded))
    b.metric("HR", int(graded["result"].astype(str).str.upper().eq("HR").sum()))
    c.metric("Profit/Loss", f"{profit:+.2f}u")
    d.metric("ROI", f"{profit / len(graded) * 100 if len(graded) else 0:+.2f}%")
    row_months = pd.to_datetime(view["game_date"], errors="coerce").dt.strftime("%Y-%m")
    months = sorted(row_months.dropna().unique(), reverse=True)
    month = st.selectbox("Table month", months + ["All months"],
                         format_func=lambda value: value if value == "All months" else
                         pd.Timestamp(f"{value}-01").strftime("%B %Y"),
                         key=f"signal_history_month_{selected}")
    # Filter after accumulation so the selected month retains its opening balance.
    table_view = view if month == "All months" else view[row_months.eq(month)]
    columns = ["game_date", "player", "signal", "result", "book_american_odds", "profit_1u", "running_profit_1u"]
    display = table_view.reindex(columns=columns)
    display_dataframe(display, hide_index=True, width="stretch", key="signal_history_newest_first_v2",
                      column_config={
                          "game_date": "Date", "player": "Player", "signal": "Signal", "result": "Result",
                          "book_american_odds": "Odds",
                          "profit_1u": st.column_config.NumberColumn("Bet P/L (1u)",
                              help="Net profit for a simulated 1-unit signal bet. Pending and void rows contribute zero."),
                          "running_profit_1u": st.column_config.NumberColumn("Cumulative P/L (u)",
                              help="All-time total for the selected signal through this row; selecting a month does not reset it. Newest first: this total equals the next row's total plus this row's Bet P/L. Same-day order is by player and signal, not settlement time."),
                      })
    filename = "signal_history.csv" if month == "All months" else f"signal_history_{month}.csv"
    st.download_button("Download Signal History CSV", table_view.to_csv(index=False).encode("utf-8-sig"),
                       filename, "text/csv")


PARLAY_SETTLED = {"HIT", "MISS", "HR", "NO HR", "NO_HR"}


def parlay_profit_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["game_date", "daily_profit_1u", "tickets", "running_profit_1u"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    settled = frame[frame["result"].astype(str).str.upper().isin(PARLAY_SETTLED)].copy()
    settled["game_date"] = pd.to_datetime(settled["game_date"], errors="coerce").dt.normalize()
    settled["profit_1u"] = pd.to_numeric(settled["profit_1u"], errors="coerce")
    settled = settled.dropna(subset=["game_date", "profit_1u"])
    daily = settled.groupby("game_date", as_index=False, sort=True).agg(
        daily_profit_1u=("profit_1u", "sum"), tickets=("profit_1u", "size"))
    daily["running_profit_1u"] = daily["daily_profit_1u"].cumsum()
    return daily.reindex(columns=columns)


def render_parlay_history(root: Path):
    import streamlit as st
    import altair as alt
    from ..theme import OLIVE, style_chart
    from ..profit_lens_app import build_parlay_history_frame
    st.subheader("Parlay History")
    chart_slot = st.container()
    legacy = build_parlay_history_frame(root).rename(columns={
        "parlay": "signal", "parlay_result": "result",
        **{f"leg{i}_player": f"leg{i}" for i in range(1, 5)}})
    path = root / "DAILY_BASEBALL" / "ledger.sqlite3"
    boundary = ledger.first_day(path)
    if boundary and not legacy.empty:
        legacy = legacy[legacy["game_date"].astype(str).lt(boundary)]
    fresh = ledger.history(path, "parlay")
    frames = [f for f in [legacy, fresh] if not f.empty]
    if not frames:
        st.info("No parlay tickets available.")
        return
    frame = pd.concat(frames, ignore_index=True)
    selected = st.selectbox("Parlay", ["All"] + sorted(frame["signal"].dropna().unique()))
    view = frame if selected == "All" else frame[frame["signal"].eq(selected)]
    view = view.sort_values(["game_date", "signal"], kind="stable").copy()
    view["profit_1u"] = pd.to_numeric(view["profit_1u"], errors="coerce")
    settled = view["result"].astype(str).str.upper().isin(PARLAY_SETTLED)
    view["running_profit_1u"] = view["profit_1u"].where(settled, 0).fillna(0).cumsum()
    graded = view[settled]
    with chart_slot:
        timeline = parlay_profit_timeline(view)
        if timeline.empty:
            st.info("No settled parlay results for this selection yet.")
        else:
            chart = alt.Chart(timeline).mark_line(color=OLIVE, point=alt.OverlayMarkDef(color=OLIVE)).encode(
                x=alt.X("game_date:T", title="Date"),
                y=alt.Y("running_profit_1u:Q", title="Cumulative P/L (u)", scale=alt.Scale(zero=True)),
                tooltip=[alt.Tooltip("game_date:T", title="Date", format="%b %d, %Y"),
                         alt.Tooltip("running_profit_1u:Q", title="Cumulative P/L (u)", format="+.2f"),
                         alt.Tooltip("daily_profit_1u:Q", title="Daily P/L (u)", format="+.2f"),
                         alt.Tooltip("tickets:Q", title="Settled tickets")])
            st.altair_chart(style_chart(chart.properties(height=300)), width="stretch", theme=None)
        st.caption(("All test groups combined" if selected == "All" else str(selected))
                   + " | Simulated 1u per settled ticket; pending and void tickets excluded.")
    profit = graded["profit_1u"].sum()
    a, b, c, d = st.columns(4)
    a.metric("Tickets", len(graded))
    b.metric("Wins", int(graded["result"].astype(str).str.upper().isin(["HIT", "HR"]).sum()))
    c.metric("Profit/Loss", f"{profit:+.2f}u")
    d.metric("ROI", f"{profit / len(graded) * 100 if len(graded) else 0:+.2f}%")
    columns = ["game_date", "leg1", "leg2", "leg3", "leg4", "result", "parlay_decimal_odds", "profit_1u", "running_profit_1u"]
    display_dataframe(view.reindex(columns=columns).fillna("").astype(str), hide_index=True, width="stretch")
    st.download_button("Download Parlay History CSV", view.to_csv(index=False).encode("utf-8-sig"),
                       "parlay_history.csv", "text/csv")
