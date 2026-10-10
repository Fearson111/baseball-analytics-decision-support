import numpy as np
from scipy.stats import beta

from .data import finite


def beta_summary(prior, n, hits, threshold, config, effective_n=None):
    effective = min(n, config.effective_sample_cap) if effective_n is None else min(effective_n, n, config.effective_sample_cap)
    a = config.prior_strength * prior + (hits / n * effective if n else 0)
    b = config.prior_strength * (1-prior) + ((n-hits) / n * effective if n else 0)
    low, high = beta.interval(config.credible_mass, a, b)
    mean = a/(a+b)
    return dict(posterior_mean=mean, posterior_median=float(beta.median(a, b)),
                posterior_lower=float(low), posterior_upper=float(high), posterior_std=float(beta.std(a, b)),
                p_positive_ev=float(beta.sf(threshold, a, b)), effective_sample_size=effective,
                posterior_strength=a+b, prior_probability=prior,
                shrinkage_amount=mean-hits/n if n else 0, alpha=a, beta=b)


def evidence(row, history, config):
    p_market = row["break_even_probability"]
    base = finite(row.get("base_model_probability"), p_market)
    prior = np.clip((p_market + base)/2, .01, .8)
    empty = history.iloc[:0]
    matching = empty
    peers = empty
    if not history.empty:
        same_price = history.price_bucket.eq(row["price_bucket"])
        same_quality = history.base_model_probability.fillna(history.break_even_probability).sub(base).abs().le(.05)
        overlap = history.signal_labels.map(lambda ls: bool(set(ls) & set(row["signal_labels"])))
        matching = history[same_price & same_quality & overlap]
        peers = history[same_price & same_quality & ~overlap]
    # Disjoint peers inform the prior; signal observations enter only the likelihood.
    if len(peers):
        prior = (30*prior + min(len(peers), 20)*peers.result_hr.mean())/(30+min(len(peers), 20))
    n, k = len(matching), int(matching.result_hr.sum()) if len(matching) else 0
    effective = min(n, 2*matching.date.nunique()) if n else 0
    result = beta_summary(prior, n, k, p_market, config, effective)
    result.update(historical_bets=n, historical_hr=k, historical_hr_rate=k/n if n else None,
                  historical_days=matching.date.nunique() if n else 0, peer_bets=len(peers),
                  price_conditioned_hr_rate=k/n if n else None,
                  mean_market_residual=float((matching.result_hr-matching.break_even_probability).mean()) if n else None)
    return result


def signal_evidence(row, history, config):
    rows = []
    for signal in row["signal_labels"]:
        group = history[history.signal_labels.map(lambda ls: signal in ls)] if not history.empty else history
        for scope, sample in [("All prices", group), ("Current price bucket", group[group.price_bucket.eq(row["price_bucket"])]) if not group.empty else ("Current price bucket", group)]:
            n = len(sample)
            k = int(sample.result_hr.sum()) if n else 0
            prior = float(sample.break_even_probability.mean()) if n else row["break_even_probability"]
            post = beta_summary(prior, n, k, row["break_even_probability"], config,
                                min(n, 2*sample.date.nunique()) if n else 0)
            from .pricing import ev
            profits = [ev(y, o) for y, o in zip(sample.result_hr, sample.american_odds)] if n else []
            rows.append(dict(signal=signal, scope=scope, bets=n, hr=k,
                             raw_hr_rate=k/n if n else None, shrunk_hr_rate=post["posterior_mean"],
                             lower=post["posterior_lower"], upper=post["posterior_upper"],
                             effective_sample_size=post["effective_sample_size"],
                             historical_roi=sum(profits)/n*100 if n else None,
                             gap_pp=(k/n-row["break_even_probability"])*100 if n else None,
                             alpha_pp=(k/n-prior)*100 if n else None))
    return rows
