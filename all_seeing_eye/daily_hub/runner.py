from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

import pandas as pd

from .markets import fetch_context, fetch_prices, is_pregame, prepare_market_board, key
from ..paths import ROOT, GBM, SEQUENCE, MATCHUP, UPSTREAM_PYTHON


HUB = ROOT / "DAILY_BASEBALL"
PYTHON = UPSTREAM_PYTHON
MATCHUP_INPUT_LIMIT = 150
STATE_SIGNAL_DAYS = 3
INPUTS = {"gbm": "gbm_top80.csv", "regression": "gbm_progression_top80.csv",
          "sequence": "sequence_top150.csv", "matchup": "pitcher_batter_top80.csv"}


def atomic_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, indent=2, default=str))
    os.replace(temp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, json.JSONDecodeError):
        return {} if default is None else default


def source_paths(day: str) -> dict[str, Path]:
    return {
        "gbm": GBM / f"data/projections/daily_hr_projections_{day}.csv",
        "regression": GBM / f"data/projections/daily_positive_regression_targets_{day}.csv",
        "sequence": SEQUENCE / f"data/processed/hr_projection_target_hr_next_game_{day}.csv",
        "matchup": MATCHUP / f"outputs/daily_optimizer/hr_edge_board_{day}.csv",
    }


def rolling_state_history(input_root: Path, before: date) -> list[tuple[date, Path]]:
    """Latest three complete prior input days, with one snapshot per day."""
    by_day = {}
    for folder in input_root.glob("manual_*"):
        if not folder.is_dir():
            continue
        try:
            day = datetime.strptime(folder.name.split("_")[1], "%Y%m%d").date()
        except (ValueError, IndexError):
            continue
        if day >= before or not all((folder / name).is_file() for name in INPUTS.values()):
            continue
        previous = by_day.get(day)
        if previous is None or (folder.stat().st_mtime_ns, folder.name) > (previous.stat().st_mtime_ns, previous.name):
            by_day[day] = folder
    return [(day, by_day[day]) for day in sorted(by_day)[-STATE_SIGNAL_DAYS:]]


def copy_state_inputs(source: Path, target: Path, run_root: Path) -> dict[str, str]:
    """Expand legacy capped hub inputs only from their exact original snapshot."""
    originals = {name: (source / filename).read_bytes() for name, filename in INPUTS.items()}
    paths = {name: source / filename for name, filename in INPUTS.items()}
    # Never substitute a later day's run or a different intraday model observation.
    for run in sorted(run_root.glob("*")):
        if run.name.startswith(".") or not run.is_dir():
            continue
        if read_json(run / "status.json").get("status") != "complete":
            continue
        if not all((run / "inputs" / INPUTS[name]).is_file()
                   and (run / "inputs" / INPUTS[name]).read_bytes() == raw
                   for name, raw in originals.items()):
            continue
        for name in ("gbm", "regression"):
            full_path = run / f"{name}_full.csv"
            if not full_path.is_file():
                continue
            archived = pd.read_csv(paths[name], dtype=str).fillna("")
            full = pd.read_csv(full_path, dtype=str).fillna("")
            if len(archived) == 80 and len(full) > 80 and full.head(80).equals(archived):
                paths[name] = full_path
        break
    for name, filename in INPUTS.items():
        shutil.copy2(paths[name], target / filename)
    return {name: str(path) for name, path in paths.items()}


@contextmanager
def snapshot_lock():
    """Serialize local rebuilds/publication, without locking out corrections during model runs."""
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "snapshot.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class Runner:
    def __init__(self, day: str, run_id: str, mode: str = "full", limit: int = 120, confirmed_only: bool = False):
        self.day, self.mode, self.limit, self.confirmed_only = day, mode, limit, confirmed_only
        self.folder = HUB / "runs" / day / run_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state = {"date": day, "run_id": run_id, "mode": mode, "status": "running", "pid": os.getpid(),
                      "started": datetime.now(timezone.utc).isoformat(), "stages": {}, "warnings": [],
                      "confirmed_only": confirmed_only, "limit": limit}
        self.mutex = threading.Lock()
        self.save()

    def save(self):
        atomic_json(self.folder / "status.json", self.state)
        if self.mode != "correction":
            atomic_json(HUB / "status.json", self.state)

    def status(self, stage: str, value: str):
        with self.mutex:
            self.state["stages"][stage] = value
            self.save()

    def warn(self, message: str):
        with self.mutex:
            self.state["warnings"].append(message)
            self.save()

    def command(self, root: Path, script: str, *args: str, label: str | None = None):
        if not (root / "scripts" / script).is_file():
            raise FileNotFoundError(
                f"Missing upstream script: {root / 'scripts' / script}. "
                "Configure MODEL4_GBM_DIR, MODEL4_SEQUENCE_DIR, and MODEL4_MATCHUP_DIR; "
                "see docs/daily_workflow.md."
            )
        stage = label or script.removesuffix(".py").replace("_", " ")
        self.status(stage, "running")
        log = self.folder / (script + ".log")
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        with log.open("a") as handle:
            process = subprocess.Popen([str(PYTHON), "-B", str(root / "scripts" / script), *args],
                                       cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                self.status(stage, "failed")
                raise RuntimeError(f"{stage} exceeded one hour. See {log.name}.") from None
        if code:
            self.status(stage, "failed")
            raise RuntimeError(f"{stage} failed (exit {code}). See {log.name}.")
        self.status(stage, "complete")

    def lineups(self):
        """Fetch today's lineup enrichment without making a transient API outage fatal."""
        output = GBM / f"data/raw/daily/lineups_{self.day}.csv"
        try:
            # The upstream script is idempotent and writes only after all requests finish.
            # A few retries cover short MLB Stats API/TLS interruptions.
            for attempt in range(3):
                try:
                    self.command(GBM, "pull_daily_lineups.py", "--date", self.day)
                    return
                except RuntimeError:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
        except RuntimeError as exc:
            # Do not use an older day's file: stale confirmed lineups are more dangerous
            # than an explicit no-lineup observation. The morning pipeline allows this.
            columns = ["game_id", "home_away", "team_id", "team", "team_abbrev", "player_id",
                       "player_name", "batting_order", "lineup_position", "lineup_status"]
            output.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=columns).to_csv(output, index=False)
            self.status("pull daily lineups", "unavailable")
            self.warn(f"Today's MLB lineup feed was unavailable after three attempts; continuing with unconfirmed lineups. {exc}")

    def gbm(self):
        yesterday = (date.fromisoformat(self.day) - timedelta(days=1)).isoformat()
        if self.mode == "full":
            for script in ("pull_statcast_windows.py", "build_recent_form_features.py"):
                self.command(GBM, script, "--end-date", yesterday)
        for script in ("pull_daily_schedule.py", "pull_active_rosters.py", "pull_daily_lineups.py"):
            if script == "pull_daily_lineups.py":
                self.lineups()
            else:
                self.command(GBM, script, "--date", self.day)
        self.command(GBM, "build_daily_features.py", "--date", self.day, "--form-date", yesterday)
        self.command(GBM, "project_daily_hr.py", "--date", self.day)
        self.command(GBM, "project_daily_hr.py", "--date", self.day, "--confirmed-only")
        self.command(GBM, "build_positive_regression_targets.py", "--date", self.day)

    def sequence(self):
        yesterday = (date.fromisoformat(self.day) - timedelta(days=1)).isoformat()
        if self.mode == "full":
            self.command(SEQUENCE, "refresh_sequence_history.py", "--statcast-end-date", yesterday)
            self.command(SEQUENCE, "build_production_motif_feature_stack_cached.py")
        self.command(SEQUENCE, "generate_projection_output.py", "--projection-date", self.day, "--top-n", "200")
        self.command(SEQUENCE, "mine_recent6_motif_triggers.py", "--matches-only", "--projection-date", self.day)

    def models(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            matchup = pool.submit(self.command, MATCHUP, "daily_optimizer_menu.py", "--date", self.day,
                                  "--pull-context", "--build-board", "--limit", str(MATCHUP_INPUT_LIMIT), label="Model 3 matchups")
            self.gbm()
            self.sequence()
            matchup.result()

    def previous_results(self):
        from ..menu import auto_update_previous_results
        yesterday = date.fromisoformat(self.day) - timedelta(days=1)
        self.status("Previous-day results and histories", "running")
        okay = auto_update_previous_results(board_root=ROOT / "MODEL4_DAILY_READS", input_root=ROOT / "inputs",
                                           output_folder=ROOT / "MODEL4_RANK_TRACKING", target_date=yesterday)
        self.status("Previous-day results and histories", "complete" if okay else "unavailable")
        from .ledger import grade
        try:
            grade(HUB / "ledger.sqlite3", GBM / "data/history/daily_results", self.day)
            from ..financial_system.history import settle as settle_financial
            settle_financial(ROOT, GBM / "data/history/daily_results", yesterday.isoformat())
        except Exception as exc:
            self.warn(f"Frozen pick grading is pending: {exc}")
        try:
            from ..financial_system.results import refresh_due
            for report in refresh_due(ROOT, yesterday.isoformat()):
                for error in report["errors"]:
                    self.warn(f"Financial results {report['day']}: {error}")
        except Exception as exc:
            self.warn(f"Portfolio box-score reconciliation is pending: {exc}")
        if not okay:
            self.warn("Previous-day grading could not finish; existing history has been retained.")

    def reuse_model_inputs(self):
        stage = "Reuse today's saved model inputs"
        self.status(stage, "running")
        candidates = []
        for path in (HUB / "runs" / self.day).glob("*/status.json"):
            state = read_json(path)
            if (state.get("date") == self.day and state.get("status") == "complete"
                    and state.get("mode") in {"full", "refresh", "correction"}):
                candidates.append((state.get("finished", state.get("started", "")), path.parent, state))
        if not candidates:
            raise ValueError("Run Daily Predictions first. A quick refresh needs today's completed model inputs.")
        _, base, state = max(candidates, key=lambda item: (item[0], item[1].name))
        if not all((base / "incoming" / f"{name}.csv").is_file() for name in INPUTS):
            raise ValueError("The latest snapshot has incomplete model inputs. Run Daily Predictions to rebuild them.")
        self.base_folder = base
        self.state["base_run"] = str(base)
        self.state["model_inputs_as_of"] = state.get("model_inputs_as_of", state.get("finished", state.get("started")))
        self.status(stage, "complete")

    def assemble(self):
        self.status("Collect four dated inputs", "running")
        sources = ({name: self.base_folder / "incoming" / f"{name}.csv" for name in INPUTS}
                   if self.mode in {"correction", "refresh"} else source_paths(self.day))
        incoming = self.folder / "incoming"
        incoming.mkdir()
        frames = {}
        manifest = {}
        for name, path in sources.items():
            if not path.exists():
                raise FileNotFoundError(f"Missing {name} output for {self.day}: {path}")
            if self.mode not in {"saved", "correction", "refresh"} and path.stat().st_mtime < datetime.fromisoformat(self.state["started"]).timestamp():
                raise ValueError(f"{name}: the upstream run did not write a fresh output for {self.day}.")
            raw = path.read_bytes()
            (incoming / f"{name}.csv").write_bytes(raw)
            frame = pd.read_csv(path, dtype=str).fillna("")
            if frame.empty:
                raise ValueError(f"{name} output for {self.day} contains no rows.")
            for col in ("game_date", "prediction_date"):
                if col in frame and set(frame[col].str[:10]) != {self.day}:
                    raise ValueError(f"{name}: output contains a different date.")
            frames[name] = frame
            manifest[name] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "rows": len(frame),
                              "source_modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
        atomic_json(self.folder / "sources.json", manifest)
        self.status("Collect four dated inputs", "complete")
        self.status("Lineups and game-specific odds", "running")
        games, starters, prices = [], [], []
        as_of = None
        if self.mode == "correction":
            base_state = read_json(self.base_folder / "status.json")
            self.state["model_inputs_as_of"] = base_state.get("model_inputs_as_of", base_state.get("started"))
            games = read_json(self.base_folder / "games.json", [])
            prices = read_json(self.base_folder / "market_quotes.json", [])
            if (self.base_folder / "starters.json").exists():
                starters = read_json(self.base_folder / "starters.json", [])
            else:
                # Older snapshots did not save raw starters. Confirm only evidenced starters.
                old_market = pd.read_csv(self.base_folder / "market_board.csv", dtype=str).fillna("")
                starters = old_market[old_market["lineup_status"].eq("confirmed")].to_dict("records")
            as_of = datetime.fromisoformat(base_state.get("market_as_of", base_state["started"]))
            for field in ("odds_provider", "book_quote_counts"):
                self.state[field] = base_state.get(field, {})
            self.state["base_run"] = str(self.base_folder)
            for warning in base_state.get("warnings", []):
                self.warn(warning)
        elif self.mode != "saved":
            games, starters = fetch_context(self.day)
            from .credentials import read_key
            provider = os.environ.get("DAILY_BASEBALL_ODDS_PROVIDER") or read_json(HUB / "settings.json").get("odds_provider", "public_comparison")
            api_key = "" if provider == "public_comparison" else read_key(provider)
            if provider == "public_comparison":
                from .public_odds import fetch_prices as provider_prices
            elif provider == "odds_papi":
                from .odds_papi import fetch_prices as provider_prices
            elif provider == "oddsblaze":
                from .oddsblaze import fetch_prices as provider_prices
            else:
                provider_prices = fetch_prices
            prices, warnings = provider_prices(games, api_key)
            if provider == "public_comparison":
                from .public_odds import align_prices, merge_quote_sources
                prices = align_prices(prices, frames["gbm"], games)
                # Public DK/Fanatics can be blocked by CDN challenges. If the user
                # has a clean odds provider configured, use it only to fill missing
                # game/player/book identities while keeping public Bet365 quotes.
                for backup, fetcher, books in (
                    ("the_odds_api", fetch_prices, ("draftkings", "fanatics")),
                    ("odds_papi", None, ("draftkings",)),
                    ("oddsblaze", None, ("draftkings", "fanatics", "bet365")),
                ):
                    if not any(book not in {p.get("book") for p in prices} for book in books):
                        continue
                    backup_key = read_key(backup)
                    if not backup_key:
                        continue
                    if fetcher is None:
                        if backup == "odds_papi":
                            from .odds_papi import fetch_prices as fetcher
                        else:
                            from .oddsblaze import fetch_prices as fetcher
                    before = len(prices)
                    supplemental, backup_warnings = fetcher(games, backup_key)
                    prices = merge_quote_sources(prices, supplemental)
                    added = len(prices) - before
                    if added:
                        warnings.append(f"{backup} backup added {added} missing sportsbook quotes.")
                    else:
                        warnings.extend(f"{backup} backup: {message}" for message in backup_warnings)
            self.state["odds_provider"] = provider
            self.state["book_quote_counts"] = {book: sum(p["book"] == book for p in prices)
                                                for book in ("draftkings", "fanatics", "bet365")}
            if provider == "public_comparison":
                filled = {book for book, count in self.state["book_quote_counts"].items() if count}
                warnings = [message for message in warnings
                            if not any(message.startswith(f"Public comparison: {book} ") and book in filled
                                       for book in ("draftkings", "fanatics", "bet365"))]
                if any(not self.state["book_quote_counts"].get(book) for book in ("draftkings", "fanatics")):
                    warnings.append("DraftKings/Fanatics backup requires a saved The Odds API, OddsPapi, or OddsBlaze key when public pages are blocked.")
            for message in warnings:
                self.warn(message)
        else:
            schedule_path = GBM / f"data/raw/daily/schedule_{self.day}.csv"
            if schedule_path.exists():
                games = pd.read_csv(schedule_path, dtype=str).fillna("").to_dict("records")
            self.warn("Saved-input preview: no live odds or lineup verification; this run is not published to history.")
        as_of = as_of or datetime.now(timezone.utc)
        if self.mode in {"full", "refresh", "correction"}:
            from .prediction_history import retain_day
            frames = retain_day(HUB / "runs" / self.day, self.folder, frames, games,
                                self.state.get("model_inputs_as_of", as_of.isoformat()), cutoff=as_of.isoformat())
            retained = self.folder / "retained_predictions"
            retained.mkdir()
            for name, frame in frames.items():
                frame.to_csv(retained / f"{name}.csv", index=False)
            self.state["retained_prediction_rows"] = {name: len(frame) for name, frame in frames.items()}
        self.state["market_as_of"] = as_of.isoformat()
        atomic_json(self.folder / "starters.json", starters)
        atomic_json(self.folder / "games.json", games)
        atomic_json(self.folder / "market_quotes.json", prices)
        market = prepare_market_board(frames["gbm"], games, starters, prices,
                                      read_json(HUB / "overrides" / f"{self.day}.json", []),
                                      live=self.mode != "saved", confirmed_only=self.confirmed_only, as_of=as_of)
        market.to_csv(self.folder / "market_board.csv", index=False)
        market[~market["ready"]].to_csv(self.folder / "pending.csv", index=False)
        self.state["ready_players"] = int(market["ready"].sum())
        self.state["pending_players"] = int((~market["ready"]).sum())
        self.status("Lineups and game-specific odds", "complete")
        input_folder = self.folder / "inputs"
        input_folder.mkdir()
        # A single player/game is chosen consistently before passing name-keyed Model 4 inputs.
        selected = market.sort_values(["ready", "start_time"], ascending=[False, True], kind="stable").copy()
        selected["_player_key"] = selected["player_name"].map(key)
        selected = selected.drop_duplicates("_player_key")
        mapping = {key(r["player_name"]): r for r in selected.to_dict("records")}
        market_fields = ["game_date", "game_id", "player_id", "team_abbrev", "opponent_abbrev", "lineup_status", "batting_order",
                         "bookmaker_used", "book_american_odds", "dk_odds", "fan_odds", "365_odds", "edge_percent",
                         "odds_source", "odds_last_update", "adjusted_hr_probability_percent", "american_betting_odds"]
        for name, filename in INPUTS.items():
            frame = selected.drop(columns="_player_key").copy() if name == "gbm" else frames[name].copy()
            frame["_name"] = frame["player_name"].map(key)
            # Scratches can leave live inputs; their original predictions remain retained.
            frame = frame[frame["_name"].map(lambda n: mapping.get(n, {}).get("lineup_status") != "out")].copy()
            if name in {"matchup", "regression"}:
                # These inputs may omit game IDs. Do not attach a Game 1 matchup to Game 2.
                repeated = set(market.loc[market.duplicated("player_id", keep=False), "player_id"])
                keep = frame.apply(lambda r: (
                    str(mapping.get(r["_name"], {}).get("player_id", "")) not in repeated
                    or key(r.get("opposing_pitcher", "")) == key(mapping.get(r["_name"], {}).get("opposing_pitcher", ""))
                ), axis=1)
                frame = frame[keep].copy()
            if name != "gbm":
                for field in market_fields:
                    frame[field] = frame["_name"].map(lambda n: mapping.get(n, {}).get(field, ""))
                frame = frame.drop_duplicates("_name")
            rank_col = "regression_rank" if name == "regression" else "projection_rank" if name == "sequence" else "rank"
            frame = frame.sort_values(rank_col, key=lambda s: pd.to_numeric(s, errors="coerce"), kind="stable")
            frame = frame.drop(columns="_name")
            # GBM/regression filenames are legacy identifiers, not top-80 cutoffs.
            eye_input = (frame.head(MATCHUP_INPUT_LIMIT) if name == "matchup"
                         else frame.head(150) if name == "sequence" else frame)
            eye_input.to_csv(input_folder / filename, index=False)
            self.state.setdefault("eye_input_rows", {})[name] = len(eye_input)
            frames[name] = frame
        for name, frame in frames.items():
            frame.to_csv(self.folder / f"{name}_full.csv", index=False)
        return input_folder, market, frames

    def score(self, inputs: Path, market: pd.DataFrame):
        from ..cli import main as score_main
        from ..io import write_reasoning_markdown
        from ..profit_lenses import build_profit_lenses_from_run
        from ..profit_parlays import build_profit_parlays_from_run
        from ..regression_misprice import build_regression_misprice_from_run
        from ..prospective_parlays import build_prospective_parlays_from_run
        self.status("Model 4 scores, acceleration, signals and parlays", "running")
        history = self.folder / "history_inputs"
        history.mkdir()
        sources = rolling_state_history(ROOT / "inputs", date.fromisoformat(self.day))
        provenance = []
        for prior, candidate in sources:
            target = history / prior.isoformat()
            target.mkdir()
            files = copy_state_inputs(candidate, target, HUB / "runs" / prior.isoformat())
            provenance.append({"date": prior.isoformat(), "source": str(candidate), "files": files})
        self.state["state_signal_days"] = [prior.isoformat() for prior, _ in sources]
        atomic_json(self.folder / "state_signal_sources.json", provenance)
        if len(sources) < STATE_SIGNAL_DAYS:
            self.warn(f"Only {len(sources)} prior complete input days available for the three-day state-signal window.")
        out = self.folder / self.day
        out.mkdir()
        score_main(["--today", str(inputs), "--history", str(history), "--out", str(out), "--limit", str(self.limit)])
        board = pd.read_csv(out / "all_seeing_eye_board.csv", dtype=str).fillna("")
        board.to_csv(out / f"MODEL4_{self.day}_BOARD.csv", index=False)
        ready = {key(n) for n in market.loc[market["ready"], "player_name"]}
        eligible = board[board["player"].map(key).isin(ready)]
        eligible_path = out / "eligible_board.csv"
        eligible.to_csv(eligible_path, index=False)
        build_profit_lenses_from_run(eligible_path, inputs, out / "PROFIT_LENSES")
        build_profit_parlays_from_run(eligible_path, inputs, out / "PROFIT_PARLAYS")
        build_prospective_parlays_from_run(eligible_path, inputs, out / "PROSPECTIVE_PARLAYS")
        build_regression_misprice_from_run(eligible_path, inputs, out / "REGRESSION_MISPRICE")
        write_reasoning_markdown(out / f"MODEL4_{self.day}_BIG_LIST.md", board.to_dict("records"))
        self.status("Model 4 scores, acceleration, signals and parlays", "complete")
        return out

    def exports(self, out: Path, market: pd.DataFrame):
        from ..profit_lens_app import (active_profit_lens_export_rows, active_regression_misprice_export_rows,
            build_active_parlay_export_frame, stats_by_group, straight_export_row)
        from ..edge_buckets import build_edge_bucket_active_rows, build_edge_bucket_history_rows, EDGE_BUCKET_COLUMNS
        from ..sequence_edge import active_signal_rows, historical_signal_rows
        self.status("Posting tables and downloads", "running")
        projections = self.folder / "projections"
        projections.mkdir()
        # Price-dependent rules use this run's exact market snapshot.
        shutil.copy2(self.folder / "gbm_full.csv", projections / f"daily_hr_projections_{self.day}.csv")
        shutil.copy2(self.folder / "regression_full.csv", projections / f"daily_positive_regression_targets_{self.day}.csv")
        edge = pd.DataFrame(build_edge_bucket_active_rows(self.day, projections_dir=projections), columns=EDGE_BUCKET_COLUMNS)
        ready_names = {key(n) for n in market.loc[market["ready"], "player_name"]}
        edge = edge[edge["player"].map(key).isin(ready_names)]
        eligible = pd.read_csv(out / "eligible_board.csv", dtype=str).fillna("")
        sequence = active_signal_rows(ROOT, self.day, board_override=eligible, bucket_override=edge)
        edge.to_csv(out / "edge_active.csv", index=False)
        sequence.to_csv(out / "sequence_active.csv", index=False)
        rows = active_profit_lens_export_rows(ROOT, out / "PROFIT_LENSES")
        rows += active_regression_misprice_export_rows(ROOT, out / "REGRESSION_MISPRICE")
        for active, history in [(edge, pd.DataFrame(build_edge_bucket_history_rows())), (sequence, historical_signal_rows(ROOT))]:
            stats = stats_by_group(history, "signal")
            for row in active.to_dict("records"):
                signal = row.get("signal", "")
                rows.append(straight_export_row(signal, row.get("player", ""), row,
                                               stats.get(signal, "0 bets, 0 HR, +0.00u, +0.00% ROI")))
        straight = pd.DataFrame(rows, columns=["signal", "player", "sportsbook", "odds", "signal_stats"])
        ready = {key(r["player_name"]): r for r in market[market["ready"]].to_dict("records")}
        straight = straight[straight["player"].map(key).isin(ready)].copy()
        # Reject stale dynamic-source odds: every published quote comes from this run's market snapshot.
        straight["odds"] = straight["player"].map(lambda p: ready[key(p)]["book_american_odds"])
        straight["sportsbook"] = straight["player"].map(lambda p: ready[key(p)]["bookmaker_used"])
        straight["team"] = straight["player"].map(lambda p: ready[key(p)]["team_abbrev"])
        straight = straight.sort_values(["player", "signal"], kind="stable")
        from .history import straight_history, stats
        current_stats = stats(straight_history(ROOT))
        straight["signal_stats"] = straight["signal"].map(lambda s: current_stats.get(s, "0 bets, 0 HR, +0.00u, +0.00% ROI"))
        straight.to_csv(out / "straight_bets.csv", index=False)
        parlay = build_active_parlay_export_frame(out / "PROFIT_PARLAYS")
        # Give repeated raw 'odds' headers unique research-safe names.
        parlay.columns = ["parlay_test_group", "leg1", "odds1", "leg2", "odds2", "leg3", "odds3", "leg4", "odds4", "parlay_odds"]
        parlay.to_csv(out / "parlays.csv", index=False)
        self.status("Posting tables and downloads", "complete")
        self.status("Financial Decision System", "running")
        from ..financial_system.engine import build as build_financial
        build_financial(ROOT, out, persist=self.mode != "saved")
        self.status("Financial Decision System", "complete")

    def publish(self, out: Path, inputs: Path):
        if self.mode in {"saved", "correction"}:
            return
        from .ledger import capture
        capture(HUB / "ledger.sqlite3", self.day, str(out),
                pd.read_csv(out / "straight_bets.csv").fillna(""),
                pd.read_csv(out / "parlays.csv").fillna(""),
                pd.read_csv(self.folder / "market_board.csv").fillna(""))
        # Never silently replace a day's frozen record with a later refresh.
        daily = ROOT / "MODEL4_DAILY_READS" / self.day
        if not daily.exists():
            shutil.copytree(out, daily)
        else:
            self.warn("Existing dated Model 4 history was preserved. The dashboard uses this new run's snapshot.")
        from ..tracker import latest_input_folder_for_date
        archived_input = ROOT / "inputs" / ("manual_" + self.day.replace("-", "") + "_hub")
        if latest_input_folder_for_date(date.fromisoformat(self.day), ROOT / "inputs") is None:
            shutil.copytree(inputs, archived_input)

    def build_snapshot(self):
        inputs, market, _ = self.assemble()
        out = self.score(inputs, market)
        self.exports(out, market)
        self.publish(out, inputs)
        self.state.update(status="complete", output=str(out), finished=datetime.now(timezone.utc).isoformat())
        atomic_json(HUB / "latest.json", self.state)

    def run(self):
        try:
            if self.mode not in {"saved", "correction"}:
                if self.day != date.today().isoformat():
                    raise ValueError("Live runs require today's date. Use Saved-input preview for an earlier date.")
                if self.mode == "full":
                    self.previous_results()
                    self.models()
                    self.state["model_inputs_as_of"] = datetime.now(timezone.utc).isoformat()
            if self.mode == "correction":
                self.build_snapshot()
            else:
                with snapshot_lock():
                    if self.mode == "refresh":
                        self.reuse_model_inputs()
                    self.build_snapshot()
        except Exception as exc:
            self.state.update(status="failed", error=str(exc), finished=datetime.now(timezone.utc).isoformat())
            import traceback
            (self.folder / "error.log").write_text(traceback.format_exc())
        finally:
            self.save()


def start_run(day: str, mode: str, *, limit: int = 120, confirmed_only: bool = False,
              api_key: str = "", refresh_minutes: int = 0, odds_provider: str = "public_comparison") -> str:
    HUB.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%H%M%S") + "_" + uuid.uuid4().hex[:6]
    command = [sys.executable, "-B", "-m", "all_seeing_eye.daily_hub.runner", "--date", day,
               "--run-id", run_id, "--mode", mode, "--limit", str(limit), "--refresh-minutes", str(refresh_minutes)]
    if confirmed_only:
        command.append("--confirmed-only")
    env = os.environ.copy()
    env["DAILY_BASEBALL_ODDS_PROVIDER"] = odds_provider
    if api_key and odds_provider != "public_comparison":
        env_name = {"oddsblaze": "ODDSBLAZE_API_KEY", "odds_papi": "ODDSPAPI_API_KEY"}.get(odds_provider, "ODDS_API_KEY")
        env[env_name] = api_key
    with (HUB / "worker.log").open("a") as log:
        subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    return run_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=["full", "refresh", "saved"], default="full")
    parser.add_argument("--limit", type=int, default=120)
    lineup = parser.add_mutually_exclusive_group()
    lineup.add_argument("--confirmed-only", action="store_true", dest="confirmed_only")
    lineup.add_argument("--allow-unconfirmed", action="store_false", dest="confirmed_only")
    parser.set_defaults(confirmed_only=False)
    parser.add_argument("--refresh-minutes", type=int, default=0)
    args = parser.parse_args()
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "pipeline.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A daily run or refresh monitor is already active.", flush=True)
            return
        atomic_json(HUB / "monitor.json", {"enabled": args.refresh_minutes > 0, "pid": os.getpid()})
        while True:
            runner = Runner(args.date, args.run_id, args.mode, args.limit, args.confirmed_only)
            runner.run()
            if args.mode == "saved" or runner.state["status"] == "failed" or args.refresh_minutes <= 0:
                break
            games = read_json(runner.folder / "games.json", [])
            if not any(is_pregame(g, datetime.now(timezone.utc)) for g in games):
                break
            next_run = time.time() + max(args.refresh_minutes, 5) * 60
            atomic_json(HUB / "monitor.json", {"enabled": True, "pid": os.getpid(), "next_refresh": next_run})
            while time.time() < next_run:
                if not read_json(HUB / "monitor.json").get("enabled") or date.today().isoformat() != args.date:
                    return
                time.sleep(1)
            args.mode = "refresh"
            args.run_id = datetime.now().strftime("%H%M%S") + "_" + uuid.uuid4().hex[:6]
        atomic_json(HUB / "monitor.json", {"enabled": False})
        if runner.state["status"] == "failed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
