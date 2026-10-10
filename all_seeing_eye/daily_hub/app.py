from __future__ import annotations
from ..table_display import display_name

from datetime import date, datetime, timezone
import importlib.util
import os
from pathlib import Path
import sys

import pandas as pd
from ..table_display import dataframe as display_dataframe, display_frame
import streamlit as st

from ..retired_signals import without_retired_signals
from .presentation import posting_frame, table_html, excel_bytes, png_bytes
from .runner import ROOT, HUB, GBM, SEQUENCE, MATCHUP, read_json, atomic_json, start_run


def alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return without_retired_signals(pd.read_csv(path, dtype=str).fillna(""))


def controls():
    with st.sidebar:
        st.header("Daily Run")
        day = st.date_input("Slate date", value=date.today()).isoformat()
        limit = st.number_input("Eye output limit", min_value=1, max_value=500, value=120, step=10)
        confirmed = st.checkbox("Confirmed starters only for bets", value=False, key="hub_confirmed_only_v2")
        refresh = st.selectbox("Automatic lineup and odds refresh", [0, 15, 30, 60],
                               format_func=lambda n: "Off" if n == 0 else f"Every {n} minutes")
        with st.expander("Odds Connection", expanded=False):
            from .credentials import read_key, save_key
            providers = {"public_comparison": "Public comparison (no key)", "the_odds_api": "The Odds API", "odds_papi": "OddsPapi", "oddsblaze": "OddsBlaze"}
            saved_provider = read_json(HUB / "settings.json").get("odds_provider", "public_comparison")
            if saved_provider not in providers:
                saved_provider = "public_comparison"
            provider = st.selectbox("Odds provider", list(providers), index=list(providers).index(saved_provider),
                                    format_func=providers.get)
            api_key = ""
            if provider == "public_comparison":
                st.caption("No API key required. Sources: ScoresAndOdds and JediBets; saved API keys can backfill DK/Fanatics if public pages are blocked.")
                if st.button("Use Public Comparison"):
                    settings = read_json(HUB / "settings.json")
                    atomic_json(HUB / "settings.json", {**settings, "odds_provider": provider})
                    st.success("Public comparison saved as the default.")
                if st.button("Check Public Odds"):
                    from .markets import fetch_context
                    from .public_odds import fetch_prices
                    try:
                        with st.spinner("Checking public home-run odds..."):
                            games, _ = fetch_context(day)
                            prices, warnings = fetch_prices(games)
                        display_dataframe(pd.DataFrame([
                            {"Sportsbook": book, "Quotes": sum(p["book"] == book for p in prices)}
                            for book in ("draftkings", "fanatics", "bet365")
                        ]), hide_index=True, width="stretch")
                        for message in warnings:
                            st.caption(message)
                    except RuntimeError as exc:
                        st.error(str(exc))
            else:
                has_key = bool(read_key(provider))
                st.caption("Saved odds connection available" if has_key else "No saved key for this provider.")
                api_key = st.text_input("Provider API key", type="password", key="hub_odds_api_" + provider)
                if st.button("Remember in macOS Keychain"):
                    try:
                        save_key(api_key, provider)
                        settings = read_json(HUB / "settings.json")
                        atomic_json(HUB / "settings.json", {**settings, "odds_provider": provider})
                        st.success("Connection saved for future runs.")
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
        state = read_json(HUB / "status.json")
        monitor = read_json(HUB / "monitor.json")
        busy = (state.get("status") == "running" and alive(state.get("pid"))) or (monitor.get("enabled") and alive(monitor.get("pid")))
        run = st.button("Run Daily Predictions", width="stretch", disabled=busy or day != date.today().isoformat())
        refresh_now = st.button("Refresh Lineups & Odds", width="stretch", disabled=busy or day != date.today().isoformat())
        with st.expander("Saved Runs", expanded=False):
            preview = st.button("Build From Saved Inputs", disabled=busy)
        if monitor.get("enabled") and st.button("Stop Automatic Refresh", width="stretch"):
            atomic_json(HUB / "monitor.json", {**monitor, "enabled": False})
            st.rerun()
        if run or refresh_now or preview:
            mode = "full" if run else "refresh" if refresh_now else "saved"
            st.session_state["hub_requested_run"] = start_run(
                day, mode, limit=int(limit), confirmed_only=confirmed,
                api_key=api_key, refresh_minutes=refresh if mode != "saved" else 0, odds_provider=provider)
            st.info("Daily worker starting.")
        if busy:
            st.caption("Background worker active. You can keep browsing.")
        st.divider()
        for title, root in [("GBM", GBM), ("Sequence", SEQUENCE), ("Matchups", MATCHUP), ("Model 4", ROOT)]:
            st.caption(f"{title}: {'connected' if root.exists() else 'missing'}")
    return day


def format_slate_date(value: str) -> str:
    slate = date.fromisoformat(value)
    suffix = "th" if 11 <= slate.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(slate.day % 10, "th")
    return f"{slate:%B} {slate.day}{suffix}, {slate.year}"


def page_header(day: str):
    st.html(f'<header class="daily-baseball-header">'
            f'<h1 id="daily-baseball">Daily Baseball</h1>'
            f'<time datetime="{date.fromisoformat(day).isoformat()}">{format_slate_date(day)}</time>'
            '</header>')


@st.fragment(run_every="3s")
def progress(show_date=True):
    state = read_json(HUB / "status.json")
    if not state:
        return
    status = state.get("status")
    if status == "running":
        if not alive(state.get("pid")):
            st.error("The daily worker stopped unexpectedly. Check Run Details and start a new run.")
        else:
            stages = state.get("stages", {})
            complete = sum(s == "complete" for s in stages.values())
            st.progress(min(complete / max(len(stages) + 3, 1), .95), text=" / ".join(k for k, v in stages.items() if v == "running"))
    elif status == "failed":
        st.error(state.get("error", "Daily run failed."))
    elif status == "complete":
        if st.session_state.get("hub_requested_run") == state.get("run_id"):
            st.session_state["hub_selected_run_" + state["date"]] = state["run_id"]
            st.session_state.pop("hub_requested_run")
        if show_date:
            with st.container(key="hub_slate_date"):
                st.caption(format_slate_date(state["date"]))
        if st.session_state.get("hub_seen_run") != state.get("run_id"):
            st.session_state["hub_seen_run"] = state.get("run_id")
            st.rerun()
    with st.expander("Run Details", expanded=status == "failed"):
        if "state_signal_days" in state:
            st.caption("State-signal input days: " + (", ".join(state["state_signal_days"]) or "None available"))
        display_dataframe(pd.DataFrame([{"Step": k, "Status": v} for k, v in state.get("stages", {}).items()]), hide_index=True, width="stretch")
        if state.get("book_quote_counts"):
            display_dataframe(pd.DataFrame([{"Sportsbook": b, "Fresh Quotes": n} for b, n in state["book_quote_counts"].items()]), hide_index=True, width="stretch")
        for warning in state.get("warnings", []):
            st.caption(warning)
        log_folder = HUB / "runs" / state.get("date", "") / state.get("run_id", "")
        logs = sorted(log_folder.glob("*.log"))
        if logs:
            selected = st.selectbox("Log", logs, format_func=lambda p: p.name)
            import re
            content = selected.read_text(errors="replace")[-14000:]
            content = re.sub(r"(?i)(apikey|api_key)=([^&\s]+)", r"\1=[hidden]", content)
            st.code(content, language="text")


def remember_run(widget_key: str, selected_key: str):
    st.session_state[selected_key] = st.session_state[widget_key]


def choose_run(day: str) -> Path | None:
    runs = []
    for state_path in sorted((HUB / "runs" / day).glob("*/status.json"), reverse=True):
        state = read_json(state_path)
        if state.get("status") == "complete" and Path(state.get("output", "")).is_dir():
            runs.append((state, Path(state["output"])))
    if not runs:
        st.info("Run Daily Predictions, or use Build From Saved Inputs to preview an existing date.")
        return None
    runs.sort(key=lambda item: item[0].get("finished", item[0].get("started", "")), reverse=True)
    runs_by_id = {state["run_id"]: (state, output) for state, output in runs}
    selected_key = "hub_selected_run_" + day
    widget_key = "_hub_snapshot_run_" + day
    if (st.session_state.pop("hub_select_latest", False)
            or st.session_state.get(selected_key) not in runs_by_id):
        st.session_state[selected_key] = runs[0][0]["run_id"]
    # Keep the run identity outside widget state, which Streamlit cleans up on other pages.
    st.session_state[widget_key] = st.session_state[selected_key]
    snapshot_label = st.empty()
    run_id = st.selectbox("Run snapshot", list(runs_by_id), key=widget_key,
                         label_visibility="collapsed", format_func=lambda run_id:
                         f"{run_id} | {runs_by_id[run_id][0]['mode']}",
                         on_change=remember_run, args=(widget_key, selected_key))
    selected_state, selected_output = runs_by_id[run_id]
    snapshot_label.caption(f"Run snapshot | {selected_state.get('ready_players', 0)} ready | "
                           f"{selected_state.get('pending_players', 0)} pending")
    if selected_state["mode"] == "saved":
        st.warning("Saved-input preview only. Prices and lineups are not live-verified; no history tickets were published.")
    return selected_output


@st.cache_data(ttl=60, show_spinner=False)
def posting_lineups(day: str):
    from .markets import fetch_context
    games, starters = fetch_context(day)
    return games, starters, datetime.now().strftime("%H:%M")


def posting_visibility(out: Path):
    from .visibility import PostingVisibility, with_lineups
    market = load_csv(out.parent / "market_board.csv")
    if out.name == date.today().isoformat():
        try:
            with st.spinner("Checking lineup status..."):
                games, starters, checked = posting_lineups(out.name)
            market = with_lineups(market, games, starters, read_json(HUB / "overrides" / f"{out.name}.json", []))
            st.caption(f"Posting lineup check: {checked}")
        except (RuntimeError, ValueError, KeyError):
            st.warning("Latest lineup check unavailable. Using this snapshot's saved lineup statuses.")
    return PostingVisibility(market)


def posting_panel(frame: pd.DataFrame, title: str, day: str, visibility=None):
    st.subheader(title)
    if frame.empty:
        st.info("No ready rows for this view.")
        return
    if title == "Straight Bets":
        from .history import straight_history, stats
        frame = frame.copy()
        summaries = stats(straight_history(ROOT))
        frame["signal_stats"] = frame["signal"].map(lambda signal: summaries.get(signal, "0 bets, 0 HR, +0.00u, +0.00% ROI"))
    is_bets = title in {"Straight Bets", "Parlays"}
    limit = 0 if is_bets else st.number_input("Posting rows", 1, max(len(frame), 25), len(frame) if title == "All-Seeing Eye" else 25, key="posting_rows_v2_" + title)
    posting_rows = frame.head(int(limit)) if limit else frame
    if visibility is not None:
        original_count = len(posting_rows)
        posting_rows = visibility.filter(posting_rows)
        frame = visibility.filter(frame)
        st.caption(f"{len(posting_rows)} shown / {original_count} generated rows")
        if posting_rows.empty:
            st.info("No confirmed players in this posting selection.")
            return
    preview = posting_frame(posting_rows, title, 0)
    st.markdown(table_html(preview), unsafe_allow_html=True)
    slug = title.lower().replace(" ", "_").replace("-", "_") + "_" + day
    import hashlib
    export_key = slug + hashlib.sha256((preview.to_csv(index=False) + frame.to_csv(index=False) + str(preview.attrs)).encode()).hexdigest()[:12]
    a, b, c = st.columns(3)
    a.download_button("Download CSV", display_frame(preview).to_csv(index=False).encode("utf-8-sig"), slug + ".csv", "text/csv")
    if b.button("Prepare Excel", key="xlsx_" + title):
        st.session_state["export_" + export_key] = excel_bytes(preview, frame)
    if "export_" + export_key in st.session_state:
        b.download_button("Download Excel", st.session_state["export_" + export_key], slug + ".xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c.download_button("Download Posting PNG", png_bytes(preview), slug + ".png", "image/png")
    with st.expander("All Rows and Columns", expanded=False):
        st.download_button("Download Research CSV", frame.to_csv(index=False).encode("utf-8-sig"), slug + "_research.csv", "text/csv")
        display_dataframe(frame, hide_index=True, width="stretch")


def rebuild_correction(out: Path, correction: dict, *, clear: bool = False):
    from .corrections import apply_correction
    try:
        with st.spinner("Updating lists from saved inputs..."):
            apply_correction(out, correction, clear=clear)
    except (RuntimeError, ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.session_state["hub_select_latest"] = True
    st.session_state["hub_correction_notice"] = "Correction cleared and lists updated." if clear else "Correction saved and lists updated."
    st.rerun()


def pending_view(out: Path):
    st.subheader("Lineups & Odds")
    market = load_csv(out.parent / "market_board.csv")
    if market.empty:
        return
    pending = market[market["ready"].ne("True")]
    cols = ["player_name", "team_abbrev", "game_id", "game_number", "start_time", "lineup_status", "bookmaker_used", "book_american_odds", "pending_reason"]
    display_dataframe(pending.reindex(columns=cols).fillna(""), hide_index=True, width="stretch")
    with st.expander("Player Corrections", expanded=False):
        player_corrections(out, market, prefix="pending")


def player_corrections(out: Path, market: pd.DataFrame, *, prefix: str, missing_only: bool = False):
    from .markets import number
    notice = st.session_state.pop("hub_correction_notice", None)
    if notice:
        st.success(notice)
    state = read_json(out.parent / "status.json")
    if out.name != date.today().isoformat() or state.get("mode") == "saved":
        st.caption("Player corrections are available on today's live snapshots.")
        return
    if market.empty:
        return
    namespace = f"{prefix}_{out.name}_{out.parent.name}"
    missing = st.toggle("Missing odds only", value=missing_only, key=namespace + "_missing")
    choices = market.copy()
    if missing:
        choices = choices[choices["book_american_odds"].map(
            lambda value: number(value) is None or abs(number(value)) < 100)
            & choices["lineup_status"].ne("out")]
    if choices.empty:
        st.info("No players are missing book odds." if missing else "No players available.")
        return
    choices = choices.sort_values(["player_name", "game_id"], kind="stable")
    rows = {(str(r["game_id"]), str(r["player_id"])): r for r in choices.to_dict("records")}
    selected = st.selectbox("Player and game", list(rows), key=namespace + "_player",
                            format_func=lambda identity: display_name(
                                f"{rows[identity]['player_name']} | {rows[identity]['team_abbrev']} | Game {identity[0]}"
                                + (" | Out" if rows[identity]["lineup_status"] == "out" else "")))
    row = rows[selected]
    overrides = read_json(HUB / "overrides" / f"{out.name}.json", [])
    override = next((r for r in overrides if (str(r["game_id"]), str(r["player_id"])) == selected), {})
    # Separate drafts by player/game and snapshot so a prior player's odds never carry over.
    with st.form(namespace + "_" + "_".join(selected), border=False):
        a, b = st.columns(2)
        current_odds = number(row.get("book_american_odds"))
        odds = a.text_input("American odds", value=f"{current_odds:+g}" if current_odds is not None else "",
                            placeholder="+450")
        books = ["DraftKings", "Fanatics", "Bet365", "Other"]
        current_book = row.get("bookmaker_used") or "DraftKings"
        book = b.selectbox("Sportsbook", books, index=books.index(current_book) if current_book in books else 3)
        out_today = st.checkbox("Out / do not play this game", value=bool(override.get("out")))
        a, b = st.columns(2)
        save = a.form_submit_button("Save Correction", icon=":material/check:", type="primary")
        clear = b.form_submit_button("Clear Correction", icon=":material/undo:", disabled=not override)
    if clear:
        rebuild_correction(out, {"game_id": selected[0], "player_id": selected[1]}, clear=True)
    elif save:
        value = None if out_today else number(odds)
        if not out_today and (value is None or abs(value) < 100 or not value.is_integer()):
            st.error("Enter whole-number American odds such as +450 or -110, or mark the player out.")
        else:
            rebuild_correction(out, {"game_id": selected[0], "player_id": selected[1], "odds": value,
                                    "sportsbook": book, "out": out_today,
                                    "updated": datetime.now(timezone.utc).isoformat()})


def sequence_page(visibility=None, slate_date=None):
    script_dir = str(SEQUENCE / "scripts")
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    if "_hub_sequence_dashboard" not in sys.modules:
        spec = importlib.util.spec_from_file_location("_hub_sequence_dashboard", SEQUENCE / "scripts/projection_dashboard.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    def apply_visibility(frame, projection_date):
        if str(projection_date) != slate_date:
            st.warning("Select a Sequence projection file matching the slate date to use the posting lineup filter.")
            return frame.iloc[0:0].copy()
        return visibility.filter(frame)
    from ..table_display import sequence_dataframe
    sys.modules["_hub_sequence_dashboard"].main(posting_filter=apply_visibility if visibility is not None else None, table_renderer=sequence_dataframe)


def main():
    st.set_page_config(page_title="Daily Baseball", layout="wide")
    if st.session_state.pop("hub_theme_changed", False):
        st.rerun()
    from ..theme import apply_theme
    sequence = st.session_state.get("hub_page") == "Sequence Lab"
    apply_theme(enabled=not sequence)
    if sequence:
        st.title("Daily Baseball")
    day = controls()
    if not sequence:
        page_header(day)
    progress(show_date=sequence)
    labels = ["Daily Board", "Straight Bets", "Parlays", "All-Seeing Eye", "GBM Top Hitters", "Positive Regression", "Matchups", "Sequence Lab", "Model 4 Signals & History", "Financial Decision System", "Signal History", "Parlay History", "Lineups & Odds"]
    current = st.session_state.get("hub_page", labels[0])
    for start in range(0, len(labels), 4):
        columns = st.columns(4)
        for col, label in zip(columns, labels[start:start + 4]):
            col.button(label, key="hub_nav_" + label, width="stretch",
                       type="primary" if current == label and current != "Sequence Lab" else "secondary",
                       on_click=select_page, args=(label,))
    st.divider()
    hide_unconfirmed = st.toggle("Hide unconfirmed players from posting", value=False, key="hub_hide_unconfirmed_posting")
    if hide_unconfirmed and current not in {"Signal History", "Parlay History", "Lineups & Odds"}:
        if st.button("Update posting lineups", icon=":material/refresh:"):
            posting_lineups.clear()
    if current == "Sequence Lab":
        out = choose_run(day) if hide_unconfirmed else None
        if hide_unconfirmed and out is None:
            return
        sequence_page(posting_visibility(out) if out is not None and hide_unconfirmed else None, day)
        st.markdown("""<style>
        [data-testid="stButton"] button, [data-testid="stDownloadButton"] button {
          background:#25272b!important;color:#f3f3f3!important;border:1px solid #61646a!important;
          border-radius:6px!important;box-shadow:none!important;letter-spacing:0!important;}
        [data-testid="stButton"] button:hover,[data-testid="stButton"] button:focus,
        [data-testid="stButton"] button:active {background:#25272b!important;color:#f3f3f3!important;border-color:#61646a!important;}
        </style>""", unsafe_allow_html=True)
    elif current == "Financial Decision System":
        from ..financial_system.page import render
        out = choose_run(day)
        if out is not None:
            render(ROOT, out)
    elif current == "Signal History":
        from .history import render_history
        render_history(ROOT)
    elif current == "Parlay History":
        from .history import render_parlay_history
        render_parlay_history(ROOT)
    elif current == "Model 4 Signals & History":
        from ..profit_lens_app import render_app
        out = choose_run(day)
        if out is None:
            return
        from .visibility import posting_scope
        visibility = posting_visibility(out) if hide_unconfirmed else None
        with posting_scope(visibility):
            render_app(ROOT, embedded=True, daily_folder=out)
    else:
        out = choose_run(day)
        if out is None:
            return
        visibility = posting_visibility(out) if hide_unconfirmed and current != "Lineups & Odds" else None
        if current == "Lineups & Odds":
            pending_view(out)
        elif current == "Daily Board":
            status = read_json(out.parent / "status.json")
            a, b, c = st.columns(3)
            a.metric("Ready Players", status.get("ready_players", 0))
            b.metric("Pending", status.get("pending_players", 0))
            c.metric("Eye Board", len(load_csv(out / f"MODEL4_{day}_BOARD.csv")))
            posting_panel(load_csv(out / "straight_bets.csv"), "Straight Bets", day, visibility)
        else:
            files = {"Straight Bets": out / "straight_bets.csv", "Parlays": out / "parlays.csv", "All-Seeing Eye": out / f"MODEL4_{day}_BOARD.csv",
                     "GBM Top Hitters": out.parent / "gbm_full.csv", "Positive Regression": out.parent / "regression_full.csv", "Matchups": out.parent / "matchup_full.csv"}
            if current == "GBM Top Hitters":
                with st.expander("Player Corrections", expanded=True):
                    player_corrections(out, load_csv(out.parent / "market_board.csv"), prefix="gbm", missing_only=True)
            posting_panel(load_csv(files[current]), current, day, visibility)


def select_page(label):
    previous = st.session_state.get("hub_page", "Daily Board")
    st.session_state["hub_theme_changed"] = (previous == "Sequence Lab") != (label == "Sequence Lab")
    st.session_state["hub_page"] = label


if __name__ == "__main__":
    main()
