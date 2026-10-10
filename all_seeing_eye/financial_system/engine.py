from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import pandas as pd

from . import config as settings, data, posterior, meta_model, history
from .decisions import ALLOCATION_VERSION, classify, allocate
from .pricing import ev


def wager_signature(records):
    fields = ("date", "player_key", "game_id", "team", "actual_units_bet", "actual_american_odds",
              "signal_families", "model_families", "snapshot_id", "result")
    values = sorted(json.dumps(history.clean({field: row.get(field) for field in fields}), sort_keys=True)
                    for row in records)
    return hashlib.sha256(json.dumps([ALLOCATION_VERSION, values]).encode()).hexdigest()


def wagers_changed(folder, records):
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return True
    return manifest.get("wager_signature") != wager_signature(records)


def decision_export(rows):
    export = pd.DataFrame(rows)
    for column in export:
        if export[column].map(lambda value: isinstance(value, (list, dict))).any():
            export[column] = export[column].map(lambda value: json.dumps(history.clean(value)))
    return export


def synthesize(candidates, training, config, model=None, bankroll=None, existing=()):
    model = model or meta_model.train(training, config)
    rows = []
    for row in candidates.to_dict("records"):
        post = posterior.evidence(row, training, config)
        row.update(post)
        row["probability_method"] = "Price/quality-matched Beta shrinkage"
        if config.use_meta and model.get("gate_passed"):
            row.update(meta_model.uncertainty(model, row, config))
            row["probability_method"] = "Market-offset ridge / approximate Laplace uncertainty"
        row["estimated_hr_probability"] = row["posterior_mean"]
        row["final_probability"] = row["posterior_mean"]
        row["p_market"] = row["break_even_probability"]
        row["p_strabo_final"] = row["posterior_mean"]
        row["probability_edge_pp"] = 100*(row["posterior_mean"]-row["break_even_probability"])
        row["expected_value_per_unit"] = ev(row["posterior_mean"], row["american_odds"])
        row["conservative_ev"] = ev(row["posterior_lower"], row["american_odds"])
        row["model_version"] = settings.VERSION + ":" + model.get("version", "beta")
        row["config_version"] = config.signature
        row["settings_snapshot"] = asdict(config)
        row["bankroll_before"] = config.starting_bankroll if bankroll is None else bankroll
        row["training_through"] = str(training.date.max()) if not training.empty else ""
        row["decision"], row["reasons"] = classify(row, config)
        row["signal_evidence"] = posterior.signal_evidence(row, training, config)
        rows.append(row)
    return allocate(rows, config, config.starting_bankroll if bankroll is None else bankroll, existing), model


def build(root: Path, out: Path, *, config=None, persist=True, raw_history=None):
    from ..daily_hub.history import straight_history
    from ..daily_hub.runner import atomic_json
    config = (config or settings.load(root)).validate()
    raw_history = straight_history(root) if raw_history is None else raw_history
    training = data.history_players(raw_history, out.name, config)
    market = pd.read_csv(out.parent / "market_board.csv", dtype=str).fillna("")
    signals = pd.read_csv(out / "straight_bets.csv").fillna("")
    board = pd.read_csv(out / f"MODEL4_{out.name}_BOARD.csv").fillna("")
    players = data.candidates(signals, market, board, out.name, config)
    actual = history.read(root, actual=True)
    existing = actual[actual.date.eq(out.name)].to_dict("records") if not actual.empty else []
    rows, model = synthesize(players, training, config, bankroll=history.bankroll(root, config), existing=existing)
    folder = out / "FINANCIAL_SYSTEM"
    folder.mkdir(exist_ok=True)
    if persist:
        rows = history.capture(root, rows, str(folder))
    atomic_json(folder / "decisions.json", history.clean(rows))
    atomic_json(folder / "model.json", history.clean(model))
    atomic_json(root / "DAILY_BASEBALL" / "financial" / "models" / (model.get("version", "beta")+"_"+config.signature+".json"), history.clean(model))
    atomic_json(folder / "config.json", asdict(config))
    revision=hashlib.sha256(json.dumps(history.clean(rows),sort_keys=True).encode()).hexdigest()[:16]
    archive=folder/"versions"/revision
    atomic_json(archive/"decisions.json",history.clean(rows))
    atomic_json(archive/"model.json",history.clean(model))
    atomic_json(archive/"config.json",asdict(config))
    evidence=training.copy()
    for column in evidence:
        if evidence[column].map(lambda value:isinstance(value,(dict,list))).any():
            evidence[column]=evidence[column].map(lambda value:json.dumps(history.clean(value)))
    evidence.to_csv(archive/"training_player_days.csv",index=False)
    atomic_json(folder / "manifest.json", dict(config_version=config.signature, model_version=settings.VERSION,
                 training_player_days=len(training), training_through=str(training.date.max()) if len(training) else None,
                 candidates=len(players), persisted=persist, wager_signature=wager_signature(existing),
                 training_source="Retrospective raw-signal research; not prospective financial returns"))
    decision_export(rows).to_csv(folder / "decisions.csv", index=False)
    return rows, training, model

