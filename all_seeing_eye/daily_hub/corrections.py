"""Apply game-specific corrections using frozen inputs, without upstream work."""
from datetime import date, datetime
from pathlib import Path
import uuid

import pandas as pd

from . import runner


def apply_correction(out: Path, correction: dict, *, clear: bool = False) -> dict:
    day = out.name
    if day != date.today().isoformat():
        raise ValueError("Player corrections apply to today's slate only; historical snapshots stay unchanged.")
    with runner.snapshot_lock():
        # A scheduled refresh may have finished while the correction form was open.
        latest = runner.read_json(runner.HUB / "latest.json")
        if latest.get("date") == day and latest.get("status") == "complete" and latest.get("mode") != "saved":
            out = Path(latest["output"])
        base = out.parent
        state = runner.read_json(base / "status.json")
        if state.get("status") != "complete" or state.get("mode") == "saved":
            raise ValueError("Run Daily Predictions first; a saved-input preview has no verified market snapshot.")
        identity = (str(correction["game_id"]), str(correction["player_id"]))
        market = pd.read_csv(base / "market_board.csv", dtype=str).fillna("")
        identities = set(zip(market["game_id"], market["player_id"]))
        if identity not in identities:
            raise ValueError("That player/game is not in the latest snapshot. Reopen Player Corrections.")
        path = runner.HUB / "overrides" / f"{day}.json"
        rows = [r for r in runner.read_json(path, [])
                if (str(r["game_id"]), str(r["player_id"])) != identity]
        if not clear:
            rows.append(correction)
        runner.atomic_json(path, rows)
        run_id = datetime.now().strftime("%H%M%S") + "_correction_" + uuid.uuid4().hex[:6]
        limit = state.get("limit")
        if limit is None:
            limit = max(120, len(pd.read_csv(out / f"MODEL4_{day}_BOARD.csv")))
        job = runner.Runner(day, run_id, "correction", int(limit), state.get("confirmed_only", False))
        job.base_folder = base
        job.run()
        if job.state["status"] != "complete":
            raise RuntimeError("Correction saved, but the quick rebuild failed. The previous lists were retained. "
                               + job.state.get("error", "See the correction run log."))
        # Do not conceal progress or disable a separately running automatic worker.
        status = runner.read_json(runner.HUB / "status.json")
        if status.get("status") != "running":
            runner.atomic_json(runner.HUB / "status.json", job.state)
        return job.state
