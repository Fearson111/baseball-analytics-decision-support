# Daily Baseball

## Open and run

Double-click `Open Daily Baseball.command` in this project. It opens a local Streamlit dashboard on the first free port from 8510 through 8529.

1. Choose today's slate date. The Eye output defaults to 120.
2. Leave **Confirmed starters only for bets** unchecked for your normal morning run, then click **Run Daily Predictions**.
3. Review the completed boards, active signals, parlays, and pending lineup/price exceptions.
4. Download a posting PNG, formatted Excel workbook, or full research CSV.

GBM runs before Sequence. Model 3 runs alongside GBM. Model 4 starts after all four required dated input lists are available. Existing scoring formulas and signal definitions are reused. The GBM input is always the full daily projection CSV, not its separate confirmed-only CSV.

The September 4 full integration run completed in approximately six minutes. Actual timing depends on the existing models, network, and historical feature refresh.

## Prices and lineups

- Only DraftKings, Fanatics, and bet365 are eligible automatic price sources. BetRivers is never a live substitute.
- The highest available decimal-equivalent price among those books is selected and the edge is recalculated against that quote.
- **Odds Connection** defaults to **Public comparison (no key)**. It uses the public ScoresAndOdds comparison JSON plus the four-book free JediBets board (only DraftKings from those four is eligible here). It does not access member-only data. The Odds API and OddsBlaze remain optional, separately keyed providers.
- The supplied The Odds API key authenticated, but a September 4 pregame Dodgers HR-market check returned only BetRivers. Authentication does not prove usable sportsbook coverage.
- The Odds API lists Fanatics as paid-plan coverage and does not list US bet365 MLB props. The OddsBlaze adapter is implemented and fixture-tested, but needs a separate account/key and real-market coverage check.
- No subscriptions, purchases, sportsbook logins, or bets are made by this app.
- Missing quotes remain pending. The default morning mode uses the full GBM projections and allows players whose lineups have not been announced. Confirmed-only is optional, not the default. Players omitted from an announced lineup or manually marked out remain excluded in either mode.
- Use **Lineups & Odds > Player Corrections** for a game-specific manual price or out correction. **Save Correction** immediately rebuilds the active lists and downloads from the latest saved inputs, without pulling odds or regenerating the upstream models. **Clear Correction** also rebuilds immediately. The tested correction took about three seconds.
- Quick corrections retain the saved odds/lineup observation time and do not change frozen history. Use **Refresh Lineups & Odds** when you want newly fetched prices and lineup information. Automatic refresh remains available; its publication is coordinated with corrections.
- **Refresh Lineups & Odds** reuses the raw GBM, regression, Sequence, and matchup inputs from today's latest completed live snapshot. It fetches lineups and prices, then rebuilds Model 4 lists, exports, and financial recommendations without rerunning upstream models or historical feature processing. Existing manual corrections still apply. Missing or invalid same-day inputs require **Run Daily Predictions**; the quick path never substitutes another day's inputs. Model probabilities remain from the original model run (`model_inputs_as_of` in run details); use **Run Daily Predictions** to regenerate projections for changed model or matchup context. A refresh explicitly started in the dashboard selects its new snapshot when complete.
- Marked-out players are excluded from the model input pool and active outputs. The correction picker retains them so the override can be cleared.
- Optional 15/30/60-minute background refresh runs while the worker and Mac remain awake. Off is the default. It stops when no pregame games remain, the date changes, or you stop it.
- No source can supply an unpublished or suspended sportsbook market. Those entries remain pending.

## Doubleheaders

Quotes are matched by teams AND scheduled start time, then stored against MLB game ID plus player ID. Ambiguous events are withheld, not attached to both games.

Model 4's existing scoring engine is player-name keyed. To avoid mixing two games, the hub admits at most one eligible game for a hitter at a time, preferring the earliest ready game. The other game remains pending until a later refresh can select it. Matchup/regression rows with a different opposing pitcher are not silently reused for that hitter.

## Posting-only lineup toggle

- **Hide unconfirmed players from posting** is off by default. Turning it on filters current-day boards, signals, complete parlay tickets, the embedded model screens, and their posting downloads.
- A parlay is hidden if any leg is unconfirmed; legs are never removed or replaced.
- Turning it off restores the original generated rows and ranks without rerunning the models. The Eye posting view starts with the full generated board (up to the selected output limit, normally 120).
- For today's slate, the filter reads current MLB lineup status in memory, cached for one minute. **Update posting lineups** checks again without pulling odds or changing model selections. Earlier snapshots use their saved lineup status.
- History and the lineup-correction screen are not filtered. Stored CSVs and frozen tickets are not rewritten. The legacy CSV editor is read-only while the posting filter is on, with a filtered download instead of an overwrite.
- This control is separate from **Confirmed starters only for bets**, which changes eligibility when building a new run. The posting toggle only hides/shows rows that the selected run already generated.

## Views and exports

- GBM, regression, matchups, and Eye use the requested compact column names, with top 25 as the posting default and the full board retained.
- Straight bets are alphabetically grouped by player. Repeated names are blanked only on the posting sheet/image; the research data always retains every name.
- Menlo 11-point Excel, team-color name groups, readable contrasting text, and the supplied background style are built in. PNG uses a higher-resolution equivalent. Character spacing remains normal for rendering compatibility.
- Excel includes **Posting View** and **Research Data**. CSV cannot preserve colors, fonts, or grouped cell styling.
- Sequence Lab embeds the existing Model 2 dashboard and its filters. HR probabilities display as percentages with one decimal (for example, 20.3%); the underlying fractional probabilities and raw CSV data stay unchanged. Model 4 Signals & History embeds the existing Model 4 screens.
- Parlay exports retain the requested group order: four-leg, three-leg, movement (three legs first), two-leg, reinforced. Parlay odds use signed American notation. These retain the existing Model 4 correlation estimates, not verified executable same-game sportsbook ticket quotes.

## History and preservation

Every hub run gets an immutable snapshot under `DAILY_BASEBALL/runs/DATE/RUN_ID/`, including source copies/hashes, market quotes, inputs, outputs, and logs.

### Intraday prediction preservation

- Refreshing the browser never launches upstream predictions. Only **Run Daily Predictions** does; lineup/odds refresh and corrections reuse saved predictions.
- Each live run also writes `retained_predictions/{gbm,regression,sequence,matchup}.csv`. These retain earlier player/game forecasts even when a later upstream file drops a completed game. Identifiable rows use the latest observed pregame forecast, never a postgame recalculation. Source run, observation time, original rank, and pregame-verification status remain available for audit. Ambiguous identities are not silently assigned to a doubleheader game.
- Live quotes and eligibility remain separate. Finished games cannot produce new recommendations; scratches can leave live inputs without deleting their saved predictions. Missing quotes are still cleared rather than treated as live.
- GBM/regression dated files now retain the full day's pregame rows and rank against that retained universe. Model 3 stores its complete board before the Model 4 top-150 input limit. Upstream writers retain versioned CSV snapshots and freeze completed-game predictions. The Sequence application and its upstream files are unchanged; its observed predictions are retained within Model 4.
- Model 3 freezes the mean/standard deviation of its four daily normalization components on the first run using the new scorer, in `outputs/daily_optimizer/scoring_references/DATE.json`. Later roster reductions cannot change an unchanged player's score. Pitcher confirmations, batting-order changes, and changed player inputs still affect scores. This is a within-day stability fix, not a claim that the model is newly calibrated or that scores are absolute probabilities.
- `scripts/recover_daily_prediction_history.py --date YYYY-MM-DD` reconstructs observed coverage from saved live runs, with no model execution. `--publish-upstream` additionally restores GBM, regression, and matchup dated files after saving exact originals and hashes under `DAILY_BASEBALL/prediction_recovery/DATE/`. It never edits frozen Model 4 boards, ticket/wager ledgers, or Sequence files. Rows without verifiable pregame identity remain labeled research evidence; Model 3 training excludes those explicitly unverified rows. It cannot recover forecasts never saved in a snapshot.

Existing dated Model 4 history is not overwritten by a same-day hub refresh. State-signal input history for acceleration/staleness uses the three most recent complete prior input days, oldest to newest, with one four-CSV snapshot per date. Today/future inputs never enter this window. The next morning adds the newest prior input day and excludes the oldest from that run only; original archives are not deleted. If a calendar day has no complete inputs, the window uses the three most recent available input days. Fewer than three available days produces a warning rather than duplicated snapshots. Run Details shows the dates, and each run saves `state_signal_sources.json` plus its three-day `history_inputs` folder.

New published tickets are recorded in `DAILY_BASEBALL/ledger.sqlite3` at their first appearance with game IDs and frozen odds. Next-day grading waits for completed games and uses the existing no-play / one-AB pinch-hit void rules. Voided straight bets stay visible with no profit/loss; voided parlays are omitted, with no hindsight replacement player.

The hub's Signal History and Parlay History views join the legacy history to the new frozen records at the ledger's start date. Legacy research remains retrospective; subsequent frozen records are prospective. The embedded legacy Model 4 pages remain available for comparison.

Straight-bet exports derive signal statistics from the hub's actual graded history rows, excluding pending and void bets. Research profitability is not a forecast or a guarantee.

**Build From Saved Inputs** is explicitly a preview: it makes no live price/lineup claims and publishes no new history tickets.

## Other odds sources

Checked September 4, 2026:

- [The Odds API bookmaker coverage](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html): confirms the current feed's bet365 limitation and Fanatics subscription requirement.
- [OddsBlaze sportsbook coverage](https://oddsblaze.com/sportsbooks) and [odds endpoint](https://docs.oddsblaze.com/endpoints/odds/): lists DK, Fanatics, and bet365; exposes per-book pregame player markets and separately offers same-game-parlay data. The optional hub adapter accepts only fresh full-game over-0.5 HR quotes.
- [OpticOdds integration guide](https://developer.opticodds.com/docs/odds-api-getting-started-guide): another documented provider listing all three books, with per-market discovery and fixture-level pricing.
- [SportsGameOdds bookmaker catalog](https://sportsgameodds.com/bookmakers): another alternative listing all three; specific MLB HR coverage still requires validation.

Provider-wide bookmaker lists do not guarantee every MLB player prop or the exact price in a particular US state. Before paying, require a trial that returns full-game HR odds from all three target books, exact game times for doubleheaders, and fresh timestamps. Compare several prices against your own apps. Direct sportsbook scraping is not the default: login/location restrictions and changing pages make it a fragile unattended dependency.

## Local checks

`/usr/local/bin/python3 -B -m unittest discover -s tests -q`

The launcher uses the existing Python 3.13 model environment. Excel export can use the bundled Codex Python runtime when openpyxl is absent there. No Mac application bundles are modified.


## No-key public odds provider (September 5)

The live source check returned 270 bet365 and 194 DraftKings pregame home-run quotes across the September 5 slate before roster alignment. These are observed coverage counts, not promises that every player or every future slate is available. Fanatics was listed in the comparison catalog but returned no actual HR prices in that check; it remains unavailable rather than receiving another book's price.

- In **Odds Connection**, choose **Public comparison (no key)**. **Use Public Comparison** saves this selection. **Check Public Odds** checks coverage without running or changing model picks.
- **Run Daily Predictions** and **Refresh Lineups & Odds** use this provider by default when no other provider has been saved. No API credential is read or transmitted in this mode.
- ScoresAndOdds' public scoreboard provides event IDs and scheduled timestamps; the Odds Compare widget returns structured JSON. Only available, full-game over-0.5 HR quotes are accepted.
- JediBets' free board exposes four books in JSON attributes. Only its free DraftKings prices are read. Blurred/member-only cells are ignored; no trial or login is used.
- Quotes carry the actual sportsbook, source, provider event/selection ID where available, and observation timestamp into the market snapshot. Observation time is not a sportsbook last-change time, and an aggregator may lag the book. Verify the executable price in your sportsbook.
- Names are matched within one MLB game and against the daily roster. Accent/suffix normalization and a small explicit nickname map are allowed; ambiguous identities, conflicting alias prices, and initials without an exact identity are withheld.
- HTTP results are cached for at most five minutes. An expired cache is never used after a network failure. Requests are paced at one per second, with bounded timeouts. Access denials and rate limits produce warnings rather than proxy/fingerprint retries.
- A refresh retrieves current pregame snapshots. It does not subscribe to in-play streams or place bets. The existing 15/30/60-minute background refresh remains available.
- A feed outage does not make old odds fresh: missing quotes remain pending. Old run snapshots and frozen tickets remain unchanged.

The comparison parser uses `beautifulsoup4` (already installed in this Mac's model environment) only for public event metadata and embedded JSON attributes. Odds Compare prices themselves are parsed as JSON. It does not depend on Chrome or a logged-in browser for daily collection.




## Financial Decision System

The new main-menu button adds price-aware player decisions, uncertainty intervals, fractional-Kelly risk caps, a player inspector, a separate forward ledger, and calibration/risk charts. It runs after the existing daily exports; raw signals and upstream models stay unchanged. No bets are placed automatically. See [Financial Decision System](FINANCIAL_DECISION_SYSTEM.md) for settings, recording actual wagers, history definitions, chart keys, and limitations.

### Live portfolio results

While today's Financial Decision System page is open, a 30-second fragment checks MLB schedules and box scores for recorded wager games. Checks are throttled across browser sessions. They do not run prediction models or create wagers. The page must remain open and the computer awake; this is not a background service.

A validated live home run credits the recorded stake/odds provisionally, removes that player from active exposure, and refreshes the financial history and P/L charts. The saved result carries `result_provisional=true`, and the page labels live credits explicitly. Live zero-HR results never become losses or voids. A live scoring correction restores the pending position and reverses the credit; final box scores confirm or correct the outcome without double-counting it. Final results cannot be downgraded by a stale live response. Failed or incomplete API responses preserve the last saved results.

**Fetch & Grade Portfolio Results** can also perform this check manually, including frozen financial recommendations. Automatic checks cover recorded wagers only. Morning reconciliation includes older provisional wins until their games are final. This tracks model/app accounting, not confirmation that a sportsbook has paid out.
