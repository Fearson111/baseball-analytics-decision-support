"""Ridge logistic model with a fixed market-logit offset and chronological validation."""
import hashlib
import json
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit
from scipy.stats import norm

from .data import FAMILIES, finite

FEATURES = ["intercept", "base_model_logit_edge", "eye_quality", "matchup_quality", "model_quality", "sequence_quality"] + FAMILIES


def design(frame):
    values = []
    for r in frame.to_dict("records"):
        q = r["break_even_probability"]
        base = finite(r.get("base_model_probability"), q)
        quality = lambda name: max(0, 1-min(finite(r.get(name), 150), 150)/150)
        values.append([1, logit(np.clip(base, .001, .999))-logit(q), quality("eye_rank"),
                       quality("matchup_rank"), quality("model_rank"), quality("sequence_rank")]
                      + [float(f in r["signal_families"]) for f in FAMILIES])
    return np.array(values, dtype=float).reshape((-1, len(FEATURES)))


def fit(frame, config):
    x = design(frame)
    offset = logit(frame.break_even_probability.to_numpy())
    y = frame.result_hr.to_numpy()
    def objective(coef):
        z = offset + x @ coef
        loss = np.logaddexp(0, z).sum() - y @ z + config.ridge/2 * (coef @ coef)
        grad = x.T @ (expit(z)-y) + config.ridge*coef
        return loss, grad
    result = minimize(objective, np.zeros(x.shape[1]), jac=True, method="L-BFGS-B")
    if not result.success:
        raise ValueError("Meta-model optimization did not converge.")
    p = expit(offset + x @ result.x)
    hessian = (x.T * (p*(1-p))) @ x + config.ridge*np.eye(x.shape[1])
    return dict(coefficients=result.x.tolist(), covariance=np.linalg.inv(hessian).tolist(),
                features=FEATURES, train_bets=len(frame), trained_through=str(frame.date.max()))


def predict(model, frame):
    x = design(frame)
    latent = logit(frame.break_even_probability.to_numpy()) + x @ np.array(model["coefficients"])
    return expit(latent)


def train(history, config):
    if len(history) < config.min_train or history.date.nunique() < 25 or history.result_hr.nunique() < 2:
        return dict(status="insufficient_history", gate_passed=False, oos_bets=0)
    dates = sorted(history.date.unique())
    boundaries = sorted(set([int(len(dates)*f) for f in (.55, .70, .85, 1)]))
    oos = []
    for start, stop in zip(boundaries, boundaries[1:]):
        training = history[history.date.lt(dates[start])]
        testing = history[history.date.isin(dates[start:stop])]
        if len(training) < config.min_train or testing.empty or training.result_hr.nunique() < 2:
            continue
        model = fit(training, config)
        predictions = predict(model, testing)
        for row, p in zip(testing.to_dict("records"), predictions):
            oos.append(dict(date=row["date"], player=row["player"], y=row["result_hr"], p=float(p),
                            q=row["break_even_probability"], trained_through=model["trained_through"]))
    model = fit(history, config)
    market = np.mean([(r["y"]-r["q"])**2 for r in oos]) if oos else None
    final = np.mean([(r["y"]-r["p"])**2 for r in oos]) if oos else None
    model.update(status="trained", oos_bets=len(oos), market_brier=market, strabo_brier=final,
                 gate_passed=bool(len(oos)>=config.min_oos and final < market), oos_predictions=oos,
                 uncertainty_method="ridge Laplace approximation; latent SD floor 0.25")
    model["version"] = hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()[:12]
    return model


def uncertainty(model, row, config):
    import pandas as pd
    x = design(pd.DataFrame([row]))[0]
    q = row["break_even_probability"]
    mu = logit(q) + x @ np.array(model["coefficients"])
    sd = np.sqrt(x @ np.array(model["covariance"]) @ x + .25**2)
    # Gaussian quadrature integrates probability uncertainty on the logit scale.
    nodes, weights = np.polynomial.hermite.hermgauss(30)
    samples = expit(mu + np.sqrt(2)*sd*nodes)
    mean = np.dot(weights, samples)/np.sqrt(np.pi)
    variance = np.dot(weights, (samples-mean)**2)/np.sqrt(np.pi)
    z = norm.ppf((1+config.credible_mass)/2)
    return dict(latent_mu=float(mu), latent_sd=float(sd), posterior_mean=float(mean), posterior_median=float(expit(mu)),
                posterior_lower=float(expit(mu-z*sd)), posterior_upper=float(expit(mu+z*sd)),
                posterior_std=float(np.sqrt(variance)), p_positive_ev=float(norm.sf((logit(q)-mu)/sd)))


