# Financial Decision System

The new main-dashboard button opens a downstream research and risk layer. It does not change the GBM, Sequence, Matchup, Eye, raw straight-bet signals, or parlay rules. It does not place wagers.

## Daily operation

1. Run Daily Predictions as usual. Full runs, lineup/odds refreshes, and saved player corrections rebuild the financial layer after the posting exports finish.
2. Open Financial Decision System. BET, MARGINAL / WATCH, and PASS are separate lists with exact quote, book, break-even probability, final probability, uncertainty, EV, and capped stake.
3. Select a player to inspect the evidence, probability interval, historical price-conditioned statistics, deterministic reasons, and sizing calculations.
4. Rebuild Financial Decisions recalculates this layer from saved inputs only; it does not pull new prices or run the upstream models. Use the main Refresh Lineups & Odds control for fresh market data. When this tab rerenders, expired prices and started games are reclassified automatically.
5. Record Bet opens a personal bet form for the selected date. Choose or type a player, enter stake in units, American odds, and sportsbook, then Save Bet. Any player can be recorded regardless of model classification or game timing. Selecting an existing player/date offers Update Bet instead of creating a duplicate.
6. Grade Financial Bets From Saved Results grades financial history using saved results and final-game status. It does not regenerate a missing results file.
7. Fetch & Grade Portfolio Results fetches official MLB final box scores for financial positions on the selected run date only, then grades the separate financial ledger. It does not rerun models, refresh odds, or change non-financial histories. Counts include tracked forward-cohort players as well as actual wagers; only actual recorded wagers affect actual profit.
8. The normal morning stage reconciles yesterday's financial positions plus older unresolved dates. It uses the same fetch, validation, and grading functions as the portfolio button.

The global posting-visibility switch still controls posting views. Financial BET eligibility has its own configurable confirmed-starter requirement, enabled by default. Unconfirmed candidates remain visible as WATCH/PASS, rather than disappearing from the audit.

## Probability and price

- Decimal odds: positive American `1 + O/100`; negative American `1 + 100/abs(O)`.
- Break-even probability: `1 / decimal_odds`. This is the offered-price break-even point, not a vig-free estimate of true probability.
- EV per unit: `p * decimal_odds - 1`.
- Probability edge: `(p - break_even) * 100`, displayed in percentage points.
- Full Kelly: `max(0, (p * decimal_odds - 1) / (decimal_odds - 1))`.
- Fractional Kelly defaults to one quarter of full Kelly. Risk gates must pass first; sizing never rescues a rejected bet.

Multiple signal rows are collapsed to one player-day with the union of their labels. Family indicators represent distinct factors, not proven statistical independence. Shared pitch-fit signals cannot manufacture three independent observations.

### Default uncertainty model

The starting prior averages the offered-price break-even probability and available base-model probability. It is adjusted using disjoint historical peers in the same configured price bucket and within five percentage points of base-model probability. Missing base probability is flagged and blocks BET.

The likelihood uses the union of earlier player-days that share at least one exact triggered label, the same price bucket, and similar base-model probability. Each player-day contributes once. Effective observations are capped at 100 and at twice the number of distinct dates, reducing the influence of clustered samples. These are transparent modeling assumptions, not an empirically established independence correction.

The Beta posterior supplies mean, median, standard deviation, credible interval, and `P(p > break_even)`. Interval defaults to 90%. Prior strength defaults to 30. Today's raw matched hit rate is also checked against today's break-even price.

### Optional market-offset model

A small ridge-regularized logistic model uses the market logit as a fixed offset, model/rank features, and family indicators. It uses date-separated chronological validation; no fold trains on its evaluation dates. Final-fit coefficients, covariance approximation, training dates, and held-out predictions are saved.

The model is disabled by default. Even when enabled in Settings, it is used only if sufficient chronological validation rows exist and its Brier score is lower than the market benchmark. Otherwise the Beta method remains active. Its uncertainty is an approximate Laplace distribution, not an exact Bayesian posterior.

The initial real-data validation had 736 training player-days and 403 held-out observations. Market Brier was 0.15479 versus 0.15584 for the meta-model, so the gate failed. The Evidence tab recalculates and displays the relevant current model results; these numbers are not hard-coded.

## Eligibility and risk

Defaults require positive EV, at least 1.5 percentage points of edge, at least 90% posterior probability of positive EV, an interval width no greater than 20 percentage points, and at least 25 matched historical player-days. Quotes older than 60 minutes, missing timestamps, missing base probabilities, unconfirmed starters, and started/unknown games cannot produce an actionable BET.

Risk defaults are research placeholders in units: 100u starting bankroll, 1u maximum player stake, 5u daily, 2u game, 2u team, 3u signal family, and 3u model family. Change these under Settings. No dollar account balance is inferred. Recorded stakes consume the day's remaining budget; already recorded players are not recommended again. Actual stakes are records of what happened and are not silently clipped to recommendations.

The saved user configuration sets daily and signal-family caps to 4u. Daily usage counts all wagers recorded for that date, including settled wagers; settlement does not refill that day's budget. Portfolio displays recorded stake, the daily cap, and the remaining budget separately from proposed recommendations.

Eligible, unrecorded BET candidates share the available budget equally, limited by fractional Kelly, the single-player cap, bankroll, and all game/team/family/model caps. Unused shares are redistributed to eligible candidates with room remaining. Stakes are floored to 0.01u; indivisible remainder cents go in descending P(EV > 0), descending EV, then player-key order. A 0.50u remainder splits 0.25u/0.25u across two eligible players, or 0.17u/0.17u/0.16u across three. No allocation is forced when eligibility fails or all applicable capacity is exhausted.

Each position's full stake counts against every applicable family/model risk cap. Exposure charts split shared-family stakes evenly for allocation and HHI, with gross exposure also available. This avoids confusing a non-additive cap total with actual money deployed. HHI is the sum of squared exposure shares; higher values mean greater concentration.

## History and reproducibility

- `DAILY_BASEBALL/financial/history.sqlite3` stores immutable decision snapshots, the first pregame player-day cohort, explicitly recorded wagers, and settled outcomes separately.
- The first pregame capture stays frozen for fair forward comparisons. Refreshing a price or changing a threshold does not rewrite that cohort. A recorded wager can reference a newer decision, retaining the actual price and stake.
- Historical/saved-input previews do not publish financial history. Old raw-signal results are research evidence, not backfilled financial profits.
- `FINANCIAL_SYSTEM/` under each run contains decisions, model, configuration, and a manifest. Its `versions/` directory preserves revision-specific decisions, coefficients, settings, and the deduplicated historical training table.
- The actual ledger is empty until a wager is explicitly recorded. Simulated recommendations never change actual bankroll.
- Settlement requires a final game and matching game/player result. No-appearance rows and non-starting pinch-hit-only one-AB rows are Void. Missing result rows stay Pending rather than being guessed as losses or voids.
- Void wagers have zero profit and do not count toward settled ROI or calibration. Pending rows have no realized profit.
- History downloads use the same selected stake basis as the charts and include derived bankroll before/after, expected and realized profit, and an explicit simulated-versus-recorded label. Pending/void rows do not receive a fictitious settled-bankroll point.
- Settings changes do not alter stored predictions. History bankroll curves use the displayed starting-bankroll baseline; frozen decision-time bankroll and configuration remain available in snapshots.

## Tab guide and chart keys

### Decisions

Action groups, full numerical CSV, and player inspector. The probability chart contrasts market break-even, base-model probability, and final probability with its interval. Raw-versus-shrunk signal evidence makes small-sample adjustments visible.

### Evidence

Retrospective player-day performance by signal, family, price, or month; sample sizes, hit rates, posterior intervals, ROI, market residuals, and calibration statistics. Brier scores shown as `x100` retain readable precision; lower is better. Missing base-model coverage is disclosed instead of substituting the market as a fake model prediction.

### Portfolio

Current recommendations plus recorded stakes, or selectable historical dates for frozen recommendations and recorded wagers. Exposure can be grouped by game, team, signal family, model family, or price bucket. Recorded wagers have a pregame mistake-removal control.

### History & Calibration

Choose forward recommendations (simulated) or recorded wagers. Curves remain empty until genuine observations settle. The charts include:

1. Cumulative realized versus expected profit.
2. Bankroll versus its starting baseline.
3. Drawdown from the running peak, including the starting bankroll.
4. Rolling stake-weighted ROI over exactly 20, 50, or 100 settled bets.
5. Actual, Strabo-expected, and market-expected cumulative home runs.
6. Probability residuals versus Strabo and market expectations.
7. Realized-minus-expected profit residual.
8. Daily total, average, and maximum stake; table includes bankroll fraction at risk.
9. Combined market/Strabo reliability chart, identity line, sample counts, and 90% observed-rate intervals.
10. Predicted EV versus realized individual return.
11. Performance by posterior-confidence bucket.
12. Performance by price bucket.
13. Performance by overlapping signal family.
14. Performance by distinct-family count.
15. Performance by expected-value bucket.

Portfolio concentration supplies the separate exposure/HHI chart. Legends, tooltips, axis titles, and short descriptions accompany charts. Family-group results overlap and cannot be added together.

The strategy table compares the same first-captured cohort as raw flat-1u, financially filtered flat-1u, and financially sized recommendations. Risk summaries include hit rate, ROI, expected-profit residual, Brier improvement, maximum/current drawdown, recovery duration, profit factor, volatility, and explicitly unannualized experimental Sharpe-like/Sortino-like/Calmar-like ratios. Undefined ratios stay blank.

## Limits

Raw labels were mined retrospectively. Date-separated validation does not undo label-selection hindsight. A high posterior confidence is conditional on these assumptions, not a guarantee that a wager has a true edge. Market prices contain bookmaker margin. Historical conflicting prices use the shortest usable quote and are flagged; contradictory outcomes or known multi-game ambiguities are excluded. Missing historical game identity limits doubleheader analysis.

This first version deliberately does not add Markowitz optimization, closing-line value without quotes, in-play betting, automated sportsbook execution, or claims of proven profitability. Those require data and validation beyond the current sample.

## Verification

Run `/usr/local/bin/python3 -m unittest discover -s tests -q` from the Model_4 project. Focused tests cover odds, shrinkage, family collapse, chronology, gate logic, caps, immutable capture, actual-versus-simulated accounting, void settlement, expiry, and chart/export parity. Separate Streamlit fixtures exercise populated charts without inserting fake financial history.

## Portfolio display update

- Both single and multiple active positions have colored player bars. A single position also shows its readable matchup and game-cap utilization.
- Each matchup bar is split proportionally by stake, with player names, allocated units, and signed book odds inside the segments and in tooltips. Recorded bars use actual wager odds, including boosts; frozen recommendation bars use their quoted odds. Small segments abbreviate or omit text to prevent overlap. Different games in a doubleheader remain separate matchup rows.
- Current exposure includes only pending recorded wagers. Recommendations are separate until explicitly recorded. Settled/void wagers leave active exposure but remain available in historical views and still count toward that date's recorded daily budget.
- Portfolio P/L Over Time is separate from that day's allocation. Choose recorded wagers or simulated recommendations, then add/remove lines with Visible lines.
- Available lines: realized P/L, model-expected P/L, same-position flat-1u P/L, P/L high-water mark, drawdown in units, realized-minus-expected profit, and the zero break-even reference.
- These are calendar-day closing series in units, with a zero reference before the first settled day. Days between settlements stay flat. Pending and void positions are excluded; no mined historical profits are imported. The high-water mark and drawdown here use day-closing values, while the older bet-by-bet history charts retain their bet-order path.
- The flat-1u comparison uses the same selected positions and prices. Differences from realized P/L isolate stake sizing, not a different selection strategy. The expected line uses stored probabilities, not hindsight. The residual is not a confidence interval or proof of luck.
- Download Portfolio Curve CSV contains the numerical reference series under the selected actual/simulated basis.


## Portfolio-only result checks

Run `python3 scripts/refresh_financial_results.py --date YYYY-MM-DD` for the same selected-day operation without opening Streamlit.

- Official final box scores must have complete player statistics matching team plate-appearance and home-run totals. Live games, incomplete boxes, missing players, and fetch failures stay pending; existing settled outcomes are retained on failure.
- Matching uses MLB game and player IDs, including separate doubleheader games. Explicit nonappearance is Void; non-starting one-AB pinch hitters follow the existing Void policy.
- A shared file lock serializes morning and manual financial updates. Outcomes are upserted by game/player; unchanged outcomes are not rewritten. Neither action creates wagers or adds profit transactions, so repeated checks cannot count the same win twice.
- Verified final results are cached in the financial SQLite database. They take precedence over stale generic daily-result CSVs. A later official box-score check can correct an existing outcome without duplicating it.
- Morning reconciliation rechecks yesterday, including settled positions, and older pending dates. To check a later scoring correction for an older fully settled date, select that date and fetch again.
- Decision snapshots, recorded stakes, recorded prices, upstream result CSVs, and non-financial histories are not rewritten by the portfolio-only scan.


## Personal Bet Log

- Record Bet accepts any date and player without model-eligibility or game-time restrictions. Existing player/date positions can be updated; prior details are retained in an edit audit.
- Personal entries affect actual portfolio accounting, not the frozen forward recommendation cohort. Logging time is recorded without inventing a placement timestamp.
- Existing saved predictions can supply model context. Typed players without prediction context have no invented probabilities or expected returns.
- Players matched to MLB game/player IDs are graded by the portfolio result scan and morning reconciliation. Unmatched typed entries remain pending until matched.
- Existing settled outcomes apply when a bet is recorded. Actual prices and stakes determine profit; the same wager is not counted twice.

## Active Portfolio Expected ROI

The concentration header shows stake-weighted Expected ROI: expected profit divided by the same modeled wagers' stake, expressed as a percentage. Recorded positions use actual prices, including boosts. Settled positions are excluded from the active view. If an active position lacks a usable saved probability or price, the display labels the estimate as modeled-only, discloses covered positions and units, and names excluded players. Their stakes and realized P/L are never removed from actual accounting. A complete-portfolio ROI remains unavailable until every position has a usable estimate.
