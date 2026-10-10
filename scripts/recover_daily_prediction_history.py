"""Recover observed predictions, never recreate past forecasts using today's model."""
import argparse
from datetime import datetime, timezone
import hashlib
import fcntl
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from all_seeing_eye.daily_hub.prediction_history import MODELS, retain_day
from all_seeing_eye.daily_hub.runner import HUB, atomic_json, read_json, source_paths, snapshot_lock


def recover(day, publish=False):
    runs = HUB / "runs" / day
    candidates = [(read_json(p).get("finished", ""), p.parent, read_json(p)) for p in runs.glob("*/status.json")
                  if read_json(p).get("status") == "complete" and read_json(p).get("mode") in {"full", "refresh", "correction"}]
    if not candidates:
        raise ValueError(f"No immutable model snapshots available for {day}")
    _, base, state = max(candidates)
    frames = {m: pd.read_csv(base / "incoming" / f"{m}.csv", dtype=str).fillna("") for m in MODELS}
    result = retain_day(runs, base, frames, read_json(base / "games.json", []),
                        state.get("model_inputs_as_of") or state["finished"], cutoff=state["finished"])
    destination = HUB / "prediction_recovery" / day / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination.mkdir(parents=True)
    report = {"date": day, "base_run": str(base), "models": {}, "published_upstream": publish}
    sources = source_paths(day)
    for model, frame in result.items():
        frame.to_csv(destination / f"{model}.csv", index=False)
        item = {"latest_input_rows": len(frames[model]), "retained_rows": len(frame),
                "verified_pregame_rows": int(frame.prediction_pregame_verified.sum())}
        if publish and model != "sequence":
            path = sources[model]
            with path.with_suffix(".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if path.exists():
                    raw = path.read_bytes()
                    (destination / f"{model}_before.csv").write_bytes(raw)
                    item["original_sha256"] = hashlib.sha256(raw).hexdigest()
                temp = path.with_suffix(".recovery.tmp")
                frame.to_csv(temp, index=False)
                temp.replace(path)
            item["published_path"] = str(path)
        report["models"][model] = item
    atomic_json(destination / "report.json", report)
    print(report)
    print(f"Recovery evidence: {destination}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--publish-upstream", action="store_true")
    args = parser.parse_args()
    with snapshot_lock():
        recover(args.date, args.publish_upstream)
