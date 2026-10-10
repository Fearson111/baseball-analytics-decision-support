from ..table_display import display_name
"""Labeled, tooltip-rich charts using the same metric frames as exports."""
import altair as alt
import pandas as pd
import streamlit as st
from ..theme import CHART_COLORS, CORAL, OLIVE, PEACH, TEAL, style_chart

COLORS = CHART_COLORS


def show(chart, title, description):
    st.markdown(f"#### {title}")
    st.caption(description)
    st.altair_chart(style_chart(chart.properties(height=260)), width="stretch", theme=None)


def lines(frame, x, series, title, description, ylabel="Units", xlabel="Settled bet number"):
    if frame.empty:
        return
    f = frame[[x]+list(series)].rename(columns=series).melt(id_vars=x,var_name="Series",value_name=ylabel)
    chart = alt.Chart(f).mark_line(point=True).encode(
        x=alt.X(x+":Q" if x=="bet" else x+":T",title=xlabel), y=alt.Y(ylabel+":Q",title=ylabel),
        color=alt.Color("Series:N",scale=alt.Scale(range=COLORS)),
        tooltip=[alt.Tooltip(x,title=xlabel),"Series",alt.Tooltip(ylabel,format=".2f")])
    show(chart,title,description)


def bars(frame, title, description, value="roi", label="ROI (%)"):
    if frame.empty:
        st.info("No settled observations for this breakdown yet.")
        return
    chart = alt.Chart(frame).mark_bar().encode(
        y=alt.Y("group:N",title=None,sort="-x",axis=alt.Axis(labelLimit=120,minExtent=125)), x=alt.X(value+":Q",title=label),
        color=alt.condition(alt.datum[value]>=0,alt.value(OLIVE),alt.value(CORAL)),
        tooltip=["group",alt.Tooltip(value,format=".2f")]+(["bets"] if "bets" in frame else []))
    show(chart,title,description)


def reliability(frame):
    if frame.empty:
        st.info("Calibration needs settled financial observations. No historical backfill is presented as forward performance.")
        return
    points = alt.Chart(frame).mark_circle(size=95).encode(
        x=alt.X("predicted:Q",title="Mean predicted HR probability (%)",scale=alt.Scale(zero=True)),
        y=alt.Y("observed:Q",title="Observed HR rate (%)",scale=alt.Scale(zero=True)),
        color=alt.Color("model:N",scale=alt.Scale(range=COLORS)),
        tooltip=["model","bucket","bets",alt.Tooltip("predicted",format=".1f"),alt.Tooltip("observed",format=".1f")])
    intervals = alt.Chart(frame).mark_rule(opacity=.5).encode(x="predicted:Q",y="lower:Q",y2="upper:Q",color="model:N")
    identity = alt.Chart(pd.DataFrame({"p":[0,100]})).mark_line(strokeDash=[5,4],color=OLIVE).encode(x="p:Q",y="p:Q")
    show(identity+intervals+points,"Market vs Strabo calibration",
         "The dashed diagonal is perfect calibration. Points compare mean predictions with observed HR rates; whiskers are 90% Jeffreys intervals. Small buckets are noisy. Market values are raw break-even prices, not de-vigged probabilities.")


def shrinkage(frame):
    if frame.empty:
        return
    long = frame.melt(id_vars=["signal","bets"],value_vars=["raw_hr_rate","shrunk_hr_rate"],var_name="Estimate",value_name="Probability")
    long["Probability"] *= 100
    long["Estimate"] = long.Estimate.map({"raw_hr_rate":"Raw historical rate","shrunk_hr_rate":"Shrunk posterior mean"})
    chart = alt.Chart(long).mark_circle(size=85).encode(x=alt.X("Probability:Q",title="HR probability (%)"),
        y=alt.Y("signal:N",title=None,axis=alt.Axis(labelLimit=120,minExtent=125)),color=alt.Color("Estimate:N",scale=alt.Scale(range=COLORS)),
        tooltip=["signal","Estimate","bets",alt.Tooltip("Probability",format=".1f")])
    show(chart,"Raw vs shrunk signal evidence",
         "Each pair compares a historical hit rate with a Beta-shrunk estimate. Small or highly repeated samples move more toward their market benchmark. These are overlapping retrospective signals, not independent bets.")


def price_probability(row):
    values=[{"Estimate":"Market break-even","Probability":row["break_even_probability"]*100},
            {"Estimate":"Strabo final","Probability":row["estimated_hr_probability"]*100}]
    if row.get("base_model_probability") is not None:
        values.append({"Estimate":"Base HR model","Probability":row["base_model_probability"]*100})
    points=alt.Chart(pd.DataFrame(values)).mark_circle(size=150).encode(
        x=alt.X("Probability:Q",title="HR probability (%)",scale=alt.Scale(zero=True)),
        y=alt.Y("Estimate:N",title=None,axis=alt.Axis(labelLimit=120,minExtent=125)),color=alt.Color("Estimate:N",scale=alt.Scale(range=COLORS)),
        tooltip=["Estimate",alt.Tooltip("Probability",format=".1f")])
    interval=alt.Chart(pd.DataFrame([{"Estimate":"Strabo final","lower":row["posterior_lower"]*100,"upper":row["posterior_upper"]*100}])).mark_rule(strokeWidth=4,color=COLORS[0]).encode(x="lower:Q",x2="upper:Q",y=alt.Y("Estimate:N",axis=alt.Axis(labelLimit=120,minExtent=125)))
    show(interval+points,"Price and probability",
         "The market point is the probability required to break even at this quote. The horizontal interval shows uncertainty in the financial estimate under the stored model assumptions, not a guarantee of an edge.")


def player_exposure(frame):
    frame = frame.copy()
    frame["player"] = frame["player"].map(display_name)
    from ..daily_hub.presentation import TEAMS
    frame = frame.copy()
    colors = frame.team.map(lambda team: TEAMS.get(team, ("61646A", "FFFFFF")))
    frame["team_color"] = colors.map(lambda pair: "#" + pair[0])
    frame["text_color"] = colors.map(lambda pair: "#" + pair[1])
    frame["odds_label"] = pd.to_numeric(frame["american_odds"], errors="coerce").map(
        lambda odds: f"{odds:+.0f}" if pd.notna(odds) and 100 <= abs(odds) < float("inf") else "")
    frame["label"] = frame.apply(lambda r: f"{r.player}  {r.units:.2f}u" +
                                (f"  {r.odds_label}" if r.odds_label else ""), axis=1)
    frame["stake_odds"] = frame.apply(lambda r: f"{r.units:.2f}u" +
                                     (f" {r.odds_label}" if r.odds_label else ""), axis=1)
    groups = frame.groupby("group", sort=False).units.sum().sort_values(ascending=False, kind="stable")
    tooltip = [alt.Tooltip("group:N", title="Exposure group"), alt.Tooltip("player:N", title="Player"),
               alt.Tooltip("team:N", title="Team"), alt.Tooltip("units:Q", title="Allocated units", format=".2f"),
               alt.Tooltip("odds_label:N", title="Book odds"),
               alt.Tooltip("source:N", title="Position")]
    base = alt.Chart(frame).encode(
        y=alt.Y("group:N", sort=groups.index.tolist(), title=None,
                scale=alt.Scale(paddingInner=.35, paddingOuter=.2),
                axis=None),
        tooltip=tooltip)
    bars = base.mark_bar(size=40, stroke=PEACH, strokeWidth=1, cornerRadius=3).encode(
        x=alt.X("start:Q", title=None, scale=alt.Scale(domain=[0, float(groups.max())], nice=False),
                axis=None),
        x2="end:Q", color=alt.Color("team_color:N", scale=None, legend=None))
    span = "abs(scale('x', datum.end) - scale('x', datum.start))"
    single_line = f"length(datum.label) * 8 <= {span} - 16"
    narrow = f"{span} >= 40 && !({single_line})"
    labels = base.mark_text(
        align="center", baseline="middle", font="Source Sans", fontSize=16, fontWeight=600,
        limit=alt.ExprRef(expr="max(0, abs(scale('x', datum.end) - scale('x', datum.start)) - 16)")
    ).encode(x=alt.X("midpoint:Q", axis=None, title=None), color=alt.Color("text_color:N", scale=None, legend=None),
             text=alt.condition(single_line,
                                alt.Text("label:N"), alt.value("")))
    compact_names = base.mark_text(
        align="center", baseline="middle", dy=-8, font="Source Sans", fontSize=16, fontWeight=600,
        limit=alt.ExprRef(expr=f"max(0, {span} - 16)")
    ).encode(x=alt.X("midpoint:Q", axis=None, title=None), color=alt.Color("text_color:N", scale=None, legend=None),
             text=alt.condition(narrow, alt.Text("player:N"), alt.value("")))
    compact_odds = base.mark_text(
        align="center", baseline="middle", dy=9, font="Source Sans", fontSize=12, fontWeight=600,
        limit=alt.ExprRef(expr=f"max(0, {span} - 12)")
    ).encode(x=alt.X("midpoint:Q", axis=None, title=None), color=alt.Color("text_color:N", scale=None, legend=None),
             text=alt.condition(narrow, alt.Text("stake_odds:N"), alt.value("")))
    st.altair_chart(style_chart((bars+labels+compact_names+compact_odds).properties(height=alt.Step(52)), axis_label_size=12),
                   width="stretch", theme=None)


def portfolio_history(frame, series):
    if not series:
        st.info("No reference lines selected.")
        return
    long = frame[["date"]+list(series)].rename(columns=series).melt(id_vars="date", var_name="Series", value_name="Units")
    colors = {"Realized P/L": OLIVE, "Model-expected P/L": CORAL, "Flat 1u P/L": TEAL,
              "P/L high-water mark": TEAL, "Drawdown (units)": CORAL,
              "Realized minus expected": OLIVE, "Break-even": OLIVE}
    chart = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("date:T", title="Date", axis=alt.Axis(format="%b %d", tickCount=5)),
        y=alt.Y("Units:Q", title="Profit / reference (u)", scale=alt.Scale(zero=True)),
        color=alt.Color("Series:N", scale=alt.Scale(domain=list(colors), range=list(colors.values())),
                        legend=alt.Legend(values=list(series.values()))),
        strokeDash=alt.StrokeDash("Series:N", legend=None, scale=alt.Scale(
            domain=list(colors), range=[[1,0],[6,3],[3,3],[8,3],[1,0],[3,2],[2,4]])),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%b %d, %Y"), "Series:N",
                 alt.Tooltip("Units:Q", format="+.2f")])
    st.altair_chart(style_chart(chart.properties(height=320)), width="stretch", theme=None)
