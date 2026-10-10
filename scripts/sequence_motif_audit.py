"""Read-only Sequence Lab audit; all research artifacts stay in Model 4."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import binomtest, fisher_exact, norm
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from all_seeing_eye.paths import SEQUENCE

LAB = SEQUENCE
PROC = LAB / "data/processed"
TARGET = "target_hr_next_game"
SEED = 20260912
END = pd.Timestamp("2026-09-12")
HOLDOUT = pd.Timestamp("2026-08-24")
VALIDATION = pd.Timestamp("2026-08-01")
REPS = 20000


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str))


def bh(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    q = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    result = np.empty(len(p))
    result[order] = np.minimum(q, 1)
    return result


def block_interval(values, dates, seed=SEED, reps=REPS):
    """Seven-day moving-block bootstrap of a per-observation mean."""
    f = pd.DataFrame({"value": values, "date": pd.to_datetime(dates)})
    f = f.dropna()
    if f.empty:
        return dict(mean=None, low=None, high=None, p_two_sided=1.)
    days = pd.date_range(f.date.min(), f.date.max())
    sums = f.groupby("date").value.agg(["sum", "count"]).reindex(days, fill_value=0)
    rng = np.random.default_rng(seed)
    length = min(7, len(days))
    means = []
    for start in range(0, reps, 1000):
        n = min(1000, reps-start)
        starts = rng.integers(0, len(days), size=(n, int(np.ceil(len(days)/length))))
        idx = ((starts[:, :, None] + np.arange(length)) % len(days)).reshape(n, -1)[:, :len(days)]
        numerator = sums["sum"].to_numpy()[idx].sum(axis=1)
        denominator = sums["count"].to_numpy()[idx].sum(axis=1)
        valid = denominator > 0
        means.extend((numerator[valid] / denominator[valid]).tolist())
    means = np.asarray(means)
    return dict(mean=float(f.value.mean()), low=float(np.quantile(means, .025)),
                high=float(np.quantile(means, .975)),
                p_two_sided=float(min(1, 2*min((np.sum(means <= 0)+1)/(len(means)+1),
                                              (np.sum(means >= 0)+1)/(len(means)+1)))))


def guarded_excess(y, baseline, dates, players, reps=REPS):
    """Screening interval: envelope of date-block and Wilson bounds, not exact joint coverage."""
    y = np.asarray(y, dtype=float)
    baseline = np.broadcast_to(np.asarray(baseline, dtype=float), y.shape)
    if not len(y):
        return dict(mean=None, low=None, high=None, p_two_sided=1., eligible=False)
    ci = block_interval(y-baseline, dates, reps=reps)
    n, k, p0 = len(y), int(y.sum()), float(baseline.mean())
    z = norm.ppf(.975)
    center = (k/n + z*z/(2*n))/(1+z*z/n)
    half = z*np.sqrt((k/n)*(1-k/n)/n+z*z/(4*n*n))/(1+z*z/n)
    eligible = n >= 50 and pd.Series(players).nunique() >= 10
    # A zero-event empirical sample cannot imply zero underlying event risk.
    ci.update(low=min(ci["low"], center-half-p0), high=max(ci["high"], center+half-p0),
              p_two_sided=max(ci["p_two_sided"], binomtest(k,n,p0).pvalue) if eligible else 1.,
              eligible=eligible)
    return ci


def unique_game_rows(frame):
    f = frame.copy()
    for col in ("prediction_date", "next_game_date", "sequence_window_end"):
        f[col] = pd.to_datetime(f[col], errors="coerce")
    good = (f[TARGET].isin([0, 1]) & f.prediction_date.eq(f.next_game_date)
            & f.next_game_date.lt(END) & f.sequence_window_end.lt(f.prediction_date))
    f = f[good].sort_values(["prediction_date", "player_id"])
    if f.duplicated(["player_id", "next_game_id"]).any():
        raise ValueError("Duplicate player/game on the strict game-date cohort")
    return f.reset_index(drop=True)


def validate_forecast_alignment(f, forecasts):
    columns = ["prediction_date", "player_id", "next_game_id", TARGET]
    pd.testing.assert_frame_equal(f[columns].reset_index(drop=True), forecasts[columns].reset_index(drop=True),
                                  check_dtype=False, check_exact=True)


def load_data(out):
    sys.path.insert(0, str(LAB / "scripts"))
    from train_sequence_challenger_models import FEATURE_BLOCKS
    from train_baseline_control_model import add_order_free_baseline_derivatives
    source = PROC / "historical_sequence_training_dataset_14d_2026-04-08_to_2026-09-12_compact_motifs_long5_motifs_soft_ramp_rules.csv"
    selected = pd.concat([pd.read_csv(PROC / f"{kind}_selected_motifs_{TARGET}.csv").assign(family=kind)
                          for kind in ("compact", "long5")], ignore_index=True)
    selected["length"] = selected.motif.str.split(">").str.len()
    selected.to_csv(out / "original_motif_definitions.csv", index=False)
    requested = set(sum([FEATURE_BLOCKS[k] for k in ("baseline", "swing_slopes", "compact_motifs", "long5_motifs", "selected_soft_ramp_rules")], []))
    requested.update(selected.feature_name)
    requested.update(["prediction_date", "next_game_date", "next_game_id", "player_id", TARGET, "sequence_window_end"])
    requested.update(f"sequence_d{i:02d}_hr" for i in range(1, 15))
    requested.update(["sequence_d01_to_d14_quality_ahead_of_results_flag", "sequence_14d_good_air_no_hr_rate"])
    raw = pd.read_csv(source, usecols=lambda c: c in requested, low_memory=False)
    raw = add_order_free_baseline_derivatives(raw)
    f = unique_game_rows(raw)
    selected_cols = selected.feature_name.tolist()
    blocks = {k: [c for c in FEATURE_BLOCKS[k] if c in f] for k in
              ("baseline", "swing_slopes", "compact_motifs", "long5_motifs", "selected_soft_ramp_rules")}
    audit = dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), raw_rows=len(raw),
                 labeled_rows=int(raw[TARGET].notna().sum()),
                 repeated_player_next_game_rows=int(raw.dropna(subset=[TARGET]).duplicated(["player_id", "next_game_id"]).sum()),
                 unique_game_date_rows=len(f), first=str(f.prediction_date.min().date()), last=str(f.prediction_date.max().date()),
                 players=int(f.player_id.nunique()), hr=int(f[TARGET].sum()), base_rate=float(f[TARGET].mean()),
                 saved_motifs=len(selected), compact_length_counts=selected[selected.family.eq("compact")].length.value_counts().to_dict(),
                 feature_counts={k:len(v) for k,v in blocks.items()},
                 original_definition_cutoff="Original saved projection artifacts exist by June 1; June onward treated as post-discovery, not a certified timestamped preregistration.")
    fit_info_path = PROC/f"lead_baseline_plus_swing_compact_long5_soft_rules_{TARGET}_fit_info.csv"
    fit_info = pd.read_csv(fit_info_path).iloc[0]
    cutoff = str(fit_info.calibration_start)
    labeled = raw[raw[TARGET].notna() & raw.prediction_date.lt(str(END.date()))]
    original_fit = labeled[labeled.prediction_date.lt(cutoff)]
    original_cal = labeled[labeled.prediction_date.ge(cutoff)]
    fit_keys = set(zip(original_fit.player_id, original_fit.next_game_id))
    cal_keys = set(zip(original_cal.player_id, original_cal.next_game_id))
    audit["current_production_split_audit"] = dict(
        metadata_source=str(fit_info_path), calibration_start=cutoff,
        fit_rows=len(original_fit), calibration_rows=len(original_cal),
        shared_player_game_targets=len(fit_keys & cal_keys),
        calibration_rows_with_target_also_in_fit=sum(k in fit_keys for k in zip(original_cal.player_id, original_cal.next_game_id)),
        fit_rows_with_target_on_or_after_calibration_start=int(original_fit.next_game_date.ge(cutoff).sum()))
    save_json(out / "data_audit.json", audit)
    log(f"Strict cohort: {len(f):,} unique player-games; {len(raw)-len(f):,} calendar-day rows excluded")
    return f, selected, blocks


def motif_descriptives(f, selected, out):
    rows = []
    pools = {"all": np.ones(len(f), bool), "pre_June": f.prediction_date.lt("2026-06-02"),
             "post_discovery": f.prediction_date.ge("2026-06-02"), "holdout": f.prediction_date.ge(HOLDOUT)}
    pools.update({m: f.prediction_date.dt.strftime("%Y-%m").eq(m) for m in sorted(f.prediction_date.dt.strftime("%Y-%m").unique())})
    groups = {r.motif_id: f[r.feature_name].gt(0) for r in selected.itertuples()}
    groups.update(compact_any=f.sequence_compact_motif_count.gt(0), long5_any=f.sequence_long5_motif_count.gt(0),
                  either=f.sequence_compact_motif_count.gt(0) | f.sequence_long5_motif_count.gt(0),
                  both=f.sequence_compact_motif_count.gt(0) & f.sequence_long5_motif_count.gt(0))
    exact4 = selected.loc[selected.family.eq("compact") & selected.length.eq(4), "feature_name"]
    groups["exact4_any"] = f[exact4].gt(0).any(axis=1)
    for family, col in (("compact", "sequence_compact_motif"), ("long5", "sequence_long5_motif")):
        for low, high in ((1,2),(3,5),(6,8)):
            groups[f"{family}_age_{low}_{high}"] = f[col+"_count"].gt(0) & f[col+"_min_age_days"].between(low,high)
    for period, mask in pools.items():
        base = f[mask]
        for name, members in groups.items():
            sample = f[mask & members]
            rows.append(dict(period=period, motif=name, n=len(sample), hits=int(sample[TARGET].sum()),
                             players=sample.player_id.nunique(), dates=sample.prediction_date.nunique(),
                             hr_rate=sample[TARGET].mean(), base_hr_rate=base[TARGET].mean(),
                             lift=sample[TARGET].mean()/base[TARGET].mean() if len(sample) else np.nan))
    pd.DataFrame(rows).to_csv(out / "motif_period_performance.csv", index=False)


def fit_predict(f, cols, train_end, test_start, test_end):
    # A full 14-day gap avoids training on overlapping motif windows at the test boundary.
    train = f[f.prediction_date.lt(train_end)].copy()
    calibration_start = train_end - pd.Timedelta(days=14)
    fit = train[train.prediction_date.lt(calibration_start)]
    cal = train[train.prediction_date.ge(calibration_start)]
    test = f[f.prediction_date.ge(test_start) & f.prediction_date.lt(test_end)]
    assert fit.next_game_date.max() < calibration_start
    assert cal.next_game_date.max() < test_start
    model = HistGradientBoostingClassifier(learning_rate=.035, max_iter=250, max_leaf_nodes=15,
                                          l2_regularization=.1, random_state=SEED, early_stopping=False)
    model.fit(fit[cols], fit[TARGET].astype(int))
    cal_logit = logit(np.clip(model.predict_proba(cal[cols])[:,1], 1e-6, 1-1e-6)).reshape(-1,1)
    calibrator = LogisticRegression(C=1e6, max_iter=1000).fit(cal_logit, cal[TARGET].astype(int))
    if len(test):
        raw = model.predict_proba(test[cols])[:,1]
        p = calibrator.predict_proba(logit(np.clip(raw, 1e-6, 1-1e-6)).reshape(-1,1))[:,1]
    else:
        p = np.array([], dtype=float)
    artifact = dict(model=model, calibrator=calibrator, features=cols, fit_through=str(fit.prediction_date.max()),
                    calibration_through=str(cal.prediction_date.max()), test_start=str(test_start), research_only=True)
    return test.index.to_numpy(), p, artifact


def metric_row(y, p):
    return dict(n=len(y), hr=int(np.sum(y)), brier=brier_score_loss(y,p), log_loss=log_loss(y,p),
                auc=roc_auc_score(y,p), average_precision=average_precision_score(y,p),
                predicted_mean=float(np.mean(p)), actual_mean=float(np.mean(y)))


def walk_forward(f, blocks, out):
    base = blocks["baseline"] + blocks["swing_slopes"]
    variants = dict(baseline_swing=base, plus_compact=base+blocks["compact_motifs"],
                    plus_long5=base+blocks["long5_motifs"],
                    plus_both=base+blocks["compact_motifs"]+blocks["long5_motifs"],
                    production_blocks=base+blocks["compact_motifs"]+blocks["long5_motifs"]+blocks["selected_soft_ramp_rules"])
    bounds = list(pd.date_range("2026-06-15", "2026-08-24", freq="14D")) + [HOLDOUT, END]
    bounds = sorted(set(bounds))
    forecasts = f[["prediction_date", "player_id", "next_game_id", TARGET]].copy()
    fits = []
    for start,end in zip(bounds[:-1], bounds[1:]):
        for name, cols in variants.items():
            log(f"Training {name}: test {start.date()} to {(end-pd.Timedelta(days=1)).date()}")
            idx,p,artifact = fit_predict(f, cols, start-pd.Timedelta(days=14), start, end)
            forecasts.loc[idx,name] = p
            fits.append(dict(variant=name, test_start=str(start.date()), test_end=str((end-pd.Timedelta(days=1)).date()),
                             **metric_row(f.loc[idx,TARGET].to_numpy(),p)))
            if start == HOLDOUT:
                joblib.dump(artifact, out / f"shadow_{name}.joblib")
        forecasts.to_csv(out / "walk_forward_predictions.csv", index=False)
        pd.DataFrame(fits).to_csv(out / "walk_forward_folds.csv", index=False)
    summaries=[]
    for period, mask in {"all_oos": forecasts.baseline_swing.notna(), "holdout": forecasts.prediction_date.ge(HOLDOUT)}.items():
        x = forecasts[mask & forecasts.baseline_swing.notna()]
        y = x[TARGET].to_numpy()
        for name in variants:
            delta = (x[name].to_numpy()-y)**2 - (x.baseline_swing.to_numpy()-y)**2
            ci = block_interval(delta, x.prediction_date)
            summaries.append(dict(period=period, variant=name, **metric_row(y,x[name]),
                                  brier_delta_vs_baseline=ci["mean"], delta_low=ci["low"], delta_high=ci["high"],
                                  p_bootstrap=ci["p_two_sided"]))
    pd.DataFrame(summaries).to_csv(out / "walk_forward_summary.csv", index=False)
    return forecasts


def fit_latest_shadows(f, blocks, out):
    base = blocks["baseline"] + blocks["swing_slopes"]
    both = base + blocks["compact_motifs"] + blocks["long5_motifs"]
    variants = dict(baseline_swing=base, plus_both=both,
                    production_blocks=both+blocks["selected_soft_ramp_rules"])
    cards = []
    for name, cols in variants.items():
        log(f"Fresh research-only fit through September 11: {name}")
        _, _, artifact = fit_predict(f, cols, END, END, END+pd.Timedelta(days=1))
        path = out/f"latest_shadow_{name}.joblib"
        joblib.dump(artifact, path)
        cards.append(dict(variant=name, path=str(path), features=len(cols),
                          fit_through=artifact["fit_through"], calibration_through=artifact["calibration_through"],
                          fit_rows=int(f.prediction_date.lt(END-pd.Timedelta(days=14)).sum()),
                          calibration_rows=int(f.prediction_date.ge(END-pd.Timedelta(days=14)).sum()),
                          research_only=True, deployed=False))
    save_json(out/"latest_shadow_model_cards.json", cards)


def frozen_tests(f, selected, predictions, out):
    x = f.copy()
    x["baseline_prediction"] = predictions.baseline_swing
    x = x[x.baseline_prediction.notna()]
    rows=[]
    for period,mask in {"all_oos": np.ones(len(x),bool), "holdout":x.prediction_date.ge(HOLDOUT)}.items():
        z=x[mask]
        for motif in selected.itertuples():
            matches=z[z[motif.feature_name].gt(0)]
            ci=guarded_excess(matches[TARGET], matches.baseline_prediction, matches.prediction_date, matches.player_id)
            rows.append(dict(period=period,motif_id=motif.motif_id,motif=motif.motif,family=motif.family,
                             original_lift=motif.lift_vs_base,n=len(matches),players=matches.player_id.nunique(),
                             hit_rate=matches[TARGET].mean(), baseline_probability=matches.baseline_prediction.mean(),
                             residual=ci["mean"],low=ci["low"],high=ci["high"],p=ci["p_two_sided"],
                             sufficient_support=ci["eligible"]))
    result=pd.DataFrame(rows)
    for period in result.period.unique():
        ix=result.period.eq(period)
        result.loc[ix,"q_bh"]=bh(result.loc[ix,"p"])
    result.to_csv(out/"frozen_motif_cluster_tests.csv",index=False)


def load_pa(out):
    from build_historical_sequence_player_days import statcast_files, DEDUP_KEYS
    from build_sequence_features import CORE_SEQUENCE_COLUMNS, EVENT_ORDER_COLS, add_sequence_flags, ordered_statcast, outcome_token_for_pa
    cache=out/"canonical_pa_tokens.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    frames=[]
    files=statcast_files()
    manifest=[]
    for i,path in enumerate(files):
        if i % 25 == 0: log(f"Canonical PA history: file {i+1}/{len(files)}")
        for chunk in pd.read_csv(path,usecols=lambda c:c in set(CORE_SEQUENCE_COLUMNS+EVENT_ORDER_COLS),chunksize=100000,low_memory=False):
            chunk=chunk[chunk.events.notna()].copy()
            chunk["source_file"]=path.name
            frames.append(chunk)
        manifest.append(dict(path=str(path),bytes=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns))
    save_json(out/"raw_sources.json",manifest)
    pa=pd.concat(frames,ignore_index=True)
    pa["game_date"]=pd.to_datetime(pa.game_date)
    pa=pa.sort_values(["game_date","source_file"]).drop_duplicates(DEDUP_KEYS,keep="last")
    pa=ordered_statcast(add_sequence_flags(pa))
    # Use the miner's token function, not the feature builder's different vectorized tokens.
    pa["token"]=[outcome_token_for_pa(r) for r in pa.to_dict("records")]
    pa=pa[["game_date","batter","game_pk","at_bat_number","token"]]
    pa.to_pickle(cache)
    log(f"Canonical terminal plate appearances: {len(pa):,}")
    return pa


def composition_key(motif):
    mode, sequence = motif.split(":", 1)
    return mode+":"+">".join(sorted(sequence.split(">")))


def mine_candidates(f, pa, predictions, out):
    """Train-only support/lift selection; validation chooses finalists before untouched holdout."""
    pressure={"2B":"XBH","3B":"XBH","1B":"ON_BASE","FREE_PASS":"ON_BASE",
              "BARREL_OUT":"DAMAGE_OUT","GOOD_AIR_OUT":"DAMAGE_OUT","HARD_FLYOUT":"DAMAGE_OUT",
              "HARD_LINEOUT":"DAMAGE_OUT","BARREL_CONTACT":"DAMAGE_CONTACT",
              "GOOD_AIR_CONTACT":"DAMAGE_CONTACT","HARD_CONTACT":"DAMAGE_CONTACT"}
    occurrences=defaultdict(list)
    for player,group in pa.groupby("batter",sort=False):
        dates=group.game_date.to_numpy(dtype="datetime64[D]").astype(int)
        tokens=group.token.tolist()
        for length in (4,5):
            for i in range(len(tokens)-length+1):
                seq=tokens[i:i+length]
                if any(t in {"HR","PA_OTHER","PITCH"} for t in seq): continue
                for mode,parts in (("exact",seq),("pressure",[pressure.get(t,t) for t in seq])):
                    occurrences[int(player)].append((dates[i],dates[i+length-1],mode+":"+">".join(parts)))
    rowsets=[]
    for r in f.itertuples():
        day=int(np.datetime64(r.prediction_date,"D").astype(int))
        # Exact/coarse consecutive 4/5 PAs inside 14 days, completed in prior 1-3 days.
        rowsets.append({motif for start,end,motif in occurrences.get(int(r.player_id),[])
                        if start>=day-14 and day-3<=end<day})
    trainmask=f.prediction_date.lt(VALIDATION).to_numpy()
    valmask=(f.prediction_date.ge(VALIDATION)&f.prediction_date.lt(HOLDOUT)).to_numpy()
    testmask=f.prediction_date.ge(HOLDOUT).to_numpy()
    y=f[TARGET].to_numpy()
    hits=defaultdict(list)
    for i,motifs in enumerate(rowsets):
        for motif in motifs: hits[motif].append(i)
    base_train=y[trainmask].mean()
    rows=[]
    for motif,indices in hits.items():
        ids=np.array(indices)
        tr=ids[trainmask[ids]]
        if len(tr)<60 or y[tr].mean()<1.20*base_train or f.iloc[tr].player_id.nunique()<15: continue
        row=dict(motif=motif,train_n=len(tr),train_hits=int(y[tr].sum()),train_rate=y[tr].mean(),train_lift=y[tr].mean()/base_train)
        for name,mask in (("validation",valmask),("holdout",testmask)):
            z=ids[mask[ids]]
            row.update({name+"_n":len(z),name+"_hits":int(y[z].sum()),name+"_rate":y[z].mean() if len(z) else np.nan})
        va=ids[valmask[ids]]
        rest=np.flatnonzero(valmask & ~np.isin(np.arange(len(f)),va))
        row["validation_p"]=fisher_exact([[int(y[va].sum()),len(va)-int(y[va].sum())],
                                         [int(y[rest].sum()),len(rest)-int(y[rest].sum())]],alternative="greater").pvalue
        rows.append(row)
    result=pd.DataFrame(rows)
    result["validation_q"]=bh(result.validation_p)
    # Finalist ordering uses validation only, never holdout outcomes.
    result=result.sort_values(["validation_p","train_n","motif"],ascending=[True,False,True])
    result.to_csv(out/"new_motif_mining.csv",index=False)
    finalists=result[result.validation_n.ge(30)].head(10).copy()
    holdout_ci=[]
    for r in finalists.itertuples():
        ids=np.array(hits[r.motif]); ids=ids[testmask[ids]]
        ci=guarded_excess(y[ids], y[testmask].mean(), f.iloc[ids].prediction_date, f.iloc[ids].player_id)
        holdout_ci.append(dict(motif=r.motif,holdout_lift=r.holdout_rate/y[testmask].mean(),
                               holdout_players=f.iloc[ids].player_id.nunique(),
                               excess=ci["mean"],low=ci["low"],high=ci["high"],p=ci["p_two_sided"],
                               sufficient_support=ci["eligible"]))
    final=finalists.merge(pd.DataFrame(holdout_ci),on="motif")
    final["holdout_q"]=bh(final.p)
    final["promote"]=final.validation_q.le(.05)&final.holdout_q.le(.05)&final.low.gt(0)&final.sufficient_support
    final.to_csv(out/"new_motif_finalists.csv",index=False)
    # Diagnostic only: same token counts in different orders, excluding overlapping target matches.
    wanted = {composition_key(m) for m in finalists.motif}
    composition_games = defaultdict(set)
    for motif, indices in hits.items():
        key = composition_key(motif)
        if key in wanted:
            composition_games[key].update(i for i in indices if testmask[i])
    order_rows = []
    for motif in finalists.motif:
        target = {i for i in hits[motif] if testmask[i]}
        controls = composition_games[composition_key(motif)] - target
        a, b = np.array(sorted(target), dtype=int), np.array(sorted(controls), dtype=int)
        ah, bhits = int(y[a].sum()), int(y[b].sum())
        p = fisher_exact([[ah,len(a)-ah],[bhits,len(b)-bhits]], alternative="greater").pvalue if len(a) and len(b) else 1.
        order_rows.append(dict(motif=motif,exact_n=len(a),exact_hr=ah,other_orders_n=len(b),other_orders_hr=bhits,
                               exact_rate=y[a].mean() if len(a) else np.nan,
                               other_orders_rate=y[b].mean() if len(b) else np.nan,
                               exact_baseline=predictions.iloc[a].baseline_swing.mean(),
                               other_orders_baseline=predictions.iloc[b].baseline_swing.mean(),p_order_fisher=p))
    order_results = pd.DataFrame(order_rows)
    order_results["q_order_bh"] = bh(order_results.p_order_fisher)
    order_results.to_csv(out/"exploratory_order_vs_composition.csv",index=False)
    save_json(out/"mining_summary.json",dict(all_patterns=len(hits),train_screened=len(result),finalists=len(final),
                                            statistically_eligible=int(final.promote.sum()),window="14 days; completion age 1-3 days",
                                            screened_length_counts=result.motif.str.count(">").add(1).value_counts().to_dict()))
    log(f"Mined {len(hits):,} patterns; {len(result)} passed train screen; {int(final.promote.sum())} passed validation and holdout gates")


def recorded_market_audit(out):
    sys.path.insert(0,str(ROOT))
    from all_seeing_eye.daily_hub.history import straight_history
    from all_seeing_eye.sequence_edge import SIGNAL_RULES
    signals={r["signal"] for r in SIGNAL_RULES}
    records=straight_history(ROOT)
    records=records[records.signal.isin(signals)].copy()
    records=records[records.result.astype(str).str.upper().isin(["HR","NO HR","NO_HR"])]
    records=records[records.game_date.astype(str).lt(str(END.date()))]
    rows=[]
    for label,group in records.groupby("signal"):
        for period, g in [("all_saved",group),("Aug24_onward",group[group.game_date.ge(str(HOLDOUT.date()))]),
                          ("Sep05_onward",group[group.game_date.ge("2026-09-05")])]:
            pnl=pd.to_numeric(g.profit_1u,errors="coerce")
            rows.append(dict(signal=label,period=period,n=len(g),hits=int(g.result.str.upper().eq("HR").sum()),
                             pnl=pnl.sum(),roi=pnl.mean(),
                             inference="Descriptive only: small selected samples; signals overlap; not actual wagers"))
    pd.DataFrame(rows).to_csv(out/"saved_signal_market_returns.csv",index=False)
    records.to_csv(out/"saved_signal_market_tickets.csv",index=False)


def research_decisions(out):
    frozen = pd.read_csv(out/"frozen_motif_cluster_tests.csv")
    review = frozen[frozen.period.eq("all_oos")].copy()
    review["research_status"] = "unvalidated_archived_definition"
    review.loc[review.motif_id.eq("l5_05"), "research_status"] = "priority_watch_only"
    review["live_action"] = "unchanged"
    review.to_csv(out/"motif_review_decisions.csv",index=False)
    candidates = pd.read_csv(out/"new_motif_finalists.csv")
    candidates["research_status"] = np.where(candidates.validation_q.le(.05),
                                               "priority_watch_only", "exploratory_not_validated")
    candidates["live_action"] = "not_added"
    candidates.to_csv(out/"research_watchlist.csv",index=False)
    save_json(out/"change_manifest.json", dict(
        production_files_changed=[], production_models_replaced=[], signals_added=[], signals_removed=[],
        research_changes=["Unique actual-game-date training/evaluation cohort", "Target-date cutoff and chronological embargo",
                          "45 frozen motif reviews with multiplicity and small-sample gates", "Fresh exact/coarse 4/5-step mining",
                          "Order-versus-composition diagnostic", "Three updated shadow models; two include both motif families"],
        next_validation="Freeze watchlist at this audit; collect new dates with one player-game per signal and odds known before first pitch. No automatic live promotion.",
        minimum_screening_support="50 games across 10 players is a screening floor, not a power guarantee or a profitable-edge claim."))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"research/sequence_motif_audit_2026-09-12")
    parser.add_argument("--skip-training",action="store_true")
    args=parser.parse_args()
    out=args.output; out.mkdir(parents=True,exist_ok=True)
    plan_path = out/"analysis_plan.json"
    plan = dict(created_utc=datetime.now(timezone.utc).isoformat(),seed=SEED,
        holdout_start=str(HOLDOUT.date()),cutoff_exclusive=str(END.date()),bootstrap_replicates=REPS,
        unit="One player/game, prediction_date equals target game date",embargo_days=14,
        training_variants=["baseline+swing","+compact","+long5","+both","+both+soft rules"],
        primary_metric="Paired out-of-sample Brier difference; 7-day moving-block 95% CI",
        original_motif_test="45 frozen motifs: excess HR vs prior-only baseline, block bootstrap, BH FDR",
        new_mining="Train before Aug1; validation Aug1-23; final holdout Aug24-Sep11. Fresh exact/coarse 4/5-PA motifs.",
        live_changes="None; models and signals remain research-only unless validated and separately deployed")
    if not plan_path.exists():
        save_json(plan_path, plan)
    save_json(out/"methodology_revision.json", dict(updated_utc=datetime.now(timezone.utc).isoformat(),
        retrospective_research=True, no_preregistration_claim=True,
        safeguards="Discard empty bootstrap replicates; Wilson/binomial guard; >=50 games and >=10 players for motif screening; BH within each family. Market returns descriptive only.",
        exploratory_addition="Held-out exact order versus same token composition; diagnostic, not a second independent holdout."))
    with threadpool_limits(limits=4):
        f,selected,blocks=load_data(out)
        motif_descriptives(f,selected,out)
        forecasts=pd.read_csv(out/"walk_forward_predictions.csv",parse_dates=["prediction_date"]) if args.skip_training else walk_forward(f,blocks,out)
        validate_forecast_alignment(f, forecasts)
        frozen_tests(f,selected,forecasts,out)
        recorded_market_audit(out)
        pa=load_pa(out)
        mine_candidates(f,pa,forecasts,out)
        fit_latest_shadows(f,blocks,out)
        research_decisions(out)
    log("Audit complete")


if __name__=="__main__":
    main()
