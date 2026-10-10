from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone, date
import json
import random
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from all_seeing_eye.financial_system import config, data, pricing, posterior, decisions, meta_model, history, metrics, engine


def candidate(name="Player One", **changes):
    now=datetime.now(timezone.utc)
    row=dict(date=date.today().isoformat(),player=name,player_key=name.replace(" ","").lower(),
             game_id="1",player_id="10",team="SEA",opponent="CHC",american_odds=500,
             signal_labels=["Pitch-Fit Longshot + Best Eye Rank"],base_model_probability=.20,
             lineup_status="confirmed",start_time=(now+timedelta(hours=5)).isoformat(),odds_observed=now.isoformat())
    row.update(changes)
    return data.enrich(row,config.Config())


def strong(name="Player One", **changes):
    row=candidate(name,**changes)
    row.update(posterior_mean=.3,estimated_hr_probability=.3,posterior_lower=.22,posterior_upper=.38,
               posterior_std=.05,p_positive_ev=.96,historical_bets=80,historical_hr_rate=.3,
               probability_edge_pp=13.333,expected_value_per_unit=.8,decision="BET",reasons=[],
               config_version="test",model_version="test",probability_method="Price/quality-matched Beta shrinkage",
               alpha=30,beta=70,price_bucket="+500 to <+600")
    return row


class SharedAllocationTests(unittest.TestCase):
    def setUp(self):
        self.config = config.Config(max_daily=4, max_family=4, max_game=4, max_team=4, max_model=4)
        self.recorded = dict(strong("Recorded"), actual_units_bet=3.5)

    def allocate(self, rows, recorded=None, cfg=None):
        return decisions.allocate(rows, cfg or self.config, 100,
                                  [self.recorded] if recorded is None else recorded)

    def test_half_unit_remaining_goes_to_single_bettable_player(self):
        rows = self.allocate([strong("Tatis")])
        self.assertEqual(rows[0]["decision"], "BET")
        self.assertEqual(rows[0]["recommended_units"], .5)

    def test_remaining_half_or_full_unit_is_shared(self):
        for spent, expected in [(3.5, [.25, .25]), (3, [.5, .5])]:
            with self.subTest(spent=spent):
                rows = self.allocate([strong("A"), strong("B")], [{**self.recorded, "actual_units_bet": spent}])
                self.assertEqual([r["recommended_units"] for r in rows], expected)
                self.assertTrue(all(r["decision"] == "BET" for r in rows))

    def test_penny_remainder_is_deterministic_and_never_exceeds_budget(self):
        rows = self.allocate([strong("C"), strong("B"), strong("A")])
        self.assertEqual({r["player"]: r["recommended_units"] for r in rows}, {"A": .17, "B": .17, "C": .16})
        self.assertEqual(sum(r["recommended_units"] for r in rows), .5)

    def test_low_kelly_player_releases_unused_share(self):
        with patch("all_seeing_eye.financial_system.decisions.kelly", side_effect=[.004, .1]):
            rows = self.allocate([strong("A"), strong("B")])
        self.assertEqual([r["recommended_units"] for r in rows], [.1, .4])

    def test_five_half_unit_recommendations_remain_unchanged_when_budget_fits(self):
        with patch("all_seeing_eye.financial_system.decisions.kelly", return_value=.02):
            rows = self.allocate([strong(str(i)) for i in range(5)], [])
        self.assertEqual([r["recommended_units"] for r in rows], [.5] * 5)
        self.assertEqual(sum(r["recommended_units"] for r in rows), 2.5)
        self.assertTrue(all("shared allocation" not in r["stake_caps_applied"] for r in rows))

    def test_unequal_model_stakes_are_not_equalized_when_budget_fits(self):
        with patch("all_seeing_eye.financial_system.decisions.kelly", side_effect=[.02, .012, .028]):
            rows = self.allocate([strong("A"), strong("B"), strong("C")], [])
        self.assertEqual([r["recommended_units"] for r in rows], [.5, .3, .7])

    def test_recorded_and_watch_players_do_not_take_a_share(self):
        watch = dict(strong("Watch"), decision="MARGINAL / WATCH", reasons=["UNCERTAINTY_HIGH"])
        rows = self.allocate([strong("Recorded"), watch, strong("Eligible")])
        self.assertEqual([r["recommended_units"] for r in rows], [0, 0, .5])
        self.assertIn("ALREADY_RECORDED", rows[0]["reasons"])

    def test_exhausted_and_overdrawn_daily_budget_never_allocates(self):
        for spent in (4, 4.5):
            rows = self.allocate([strong("A"), strong("B")], [{**self.recorded, "actual_units_bet": spent}])
            self.assertTrue(all(r["recommended_units"] == 0 for r in rows))
            self.assertTrue(all("PORTFOLIO_CONCENTRATION" in r["reasons"] for r in rows))

    def test_shared_game_cap_does_not_strand_unrelated_capacity(self):
        cfg = replace(self.config, max_game=.2, max_daily=.6)
        rows = self.allocate([strong("A", game_id="1"), strong("B", game_id="1"),
                              strong("C", game_id="2"), strong("D", game_id="3")], [], cfg)
        self.assertEqual([r["recommended_units"] for r in rows], [.1, .1, .2, .2])

    def test_existing_model_limit_still_applies(self):
        cfg = replace(self.config, max_model=3)
        blocked = strong("GBM", signal_labels=["Book 301-400 / Edge 2.5-5%"])
        recorded = {**self.recorded, "model_families": ["GBM"], "signal_families": []}
        rows = self.allocate([blocked, strong("Other", model_families=["Matchup"])], [recorded], cfg)
        self.assertEqual([r["recommended_units"] for r in rows], [0, .5])

    def test_random_portfolios_respect_every_shared_cap(self):
        rng = random.Random(42)
        cfg = config.Config(max_daily=4, max_family=4, max_game=2, max_team=2, max_model=3)
        for trial in range(40):
            rows = [strong(str(i), game_id=str(rng.randrange(4)), team=str(rng.randrange(4)),
                           signal_families=[str(rng.randrange(3))], model_families=[str(rng.randrange(2))])
                    for i in range(rng.randrange(1, 20))]
            recorded = [dict(strong("Recorded", game_id="0", team="0", signal_families=["0"],
                                    model_families=["0"]), actual_units_bet=rng.randrange(0, 400) / 100)]
            result = decisions.allocate(rows, cfg, 100, recorded)
            with self.subTest(trial=trial):
                total = sum(r["recommended_units"] for r in result)
                self.assertLessEqual(total + recorded[0]["actual_units_bet"], 4 + 1e-9)
                for r in result:
                    self.assertLessEqual(r["recommended_units"], cfg.max_stake)
                    self.assertAlmostEqual(r["recommended_units"] * 100, round(r["recommended_units"] * 100))
                for field, limit in (("game_id", 2), ("team", 2), ("signal_families", 4), ("model_families", 3)):
                    for group in ("0", "1", "2", "3"):
                        def includes(row):
                            return group in row[field] if isinstance(row[field], list) else row[field] == group
                        spent = sum(r["actual_units_bet"] for r in recorded if includes(r))
                        added = sum(r["recommended_units"] for r in result if includes(r))
                        self.assertLessEqual(added, max(0, limit - spent) + 1e-9)


class FinancialMathTests(unittest.TestCase):
    def test_american_pricing_including_negative_prices(self):
        self.assertAlmostEqual(pricing.break_even(475),100/575)
        self.assertAlmostEqual(pricing.break_even(-110),110/210)
        self.assertAlmostEqual(pricing.ev(.2,500),.2)
        self.assertAlmostEqual(pricing.kelly(.2,500),.04)
        self.assertEqual(pricing.kelly(.1,500),0)
        for value in (0,50,float("nan"),float("inf")):
            with self.assertRaises(ValueError): pricing.break_even(value)

    def test_price_boundaries_configurable_and_complete(self):
        c=config.Config()
        self.assertEqual(pricing.bucket(500,c),"+500 to <+600")
        self.assertEqual(pricing.bucket(800,c),"+800+")
        self.assertEqual(pricing.bucket(250,c),"Below +300")
        self.assertEqual(pricing.bucket(-110,c),"Negative odds")
        self.assertNotEqual(pricing.bucket(500,replace(c,price_breaks=[300,550,800])),pricing.bucket(500,c))
        with self.assertRaises(ValueError): replace(c,price_breaks=[500,300]).validate()

    def test_beta_shrinkage_interval_probability_and_zero_data(self):
        c=config.Config(prior_strength=30)
        small=posterior.beta_summary(.15,10,5,.2,c)
        large=posterior.beta_summary(.15,100,50,.2,c)
        self.assertLess(small["posterior_mean"],large["posterior_mean"])
        self.assertLess(small["posterior_lower"],small["posterior_mean"])
        self.assertGreater(small["posterior_upper"],small["posterior_mean"])
        self.assertGreater(large["p_positive_ev"],small["p_positive_ev"])
        empty=posterior.beta_summary(.15,0,0,.2,c)
        self.assertAlmostEqual(empty["posterior_mean"],.15)

    def test_family_overlap_not_raw_votes(self):
        a=candidate(signal_labels=["Pitch-Fit Longshot + Best Eye Rank"]*3)
        self.assertEqual(a["trigger_count_raw"],1)
        self.assertEqual(a["signal_families"],data.families("Pitch-Fit Longshot + Best Eye Rank"))

    def test_history_deduplicates_and_excludes_future_conflicting_outcomes(self):
        raw=pd.DataFrame([
            dict(game_date="2026-01-01",player="Player One",signal="Rule A",result="HR",book_american_odds=600),
            dict(game_date="2026-01-01",player="Player One",signal="Rule B",result="HR",book_american_odds=500),
            dict(game_date="2026-01-02",player="Player Two",signal="Rule A",result="HR",book_american_odds=500),
            dict(game_date="2026-01-02",player="Player Two",signal="Rule B",result="No HR",book_american_odds=500),
            dict(game_date="2026-01-03",player="Player One",signal="Rule A",result="HR",book_american_odds=600)])
        f=data.history_players(raw,"2026-01-03",config.Config())
        self.assertEqual(len(f),1)
        self.assertEqual(f.iloc[0].american_odds,500)
        self.assertTrue(f.iloc[0].quote_conflict)
        self.assertEqual(f.iloc[0].signal_labels,["Rule A","Rule B"])

    def test_evidence_union_counts_each_player_day_once_and_excludes_peers(self):
        row=candidate()
        samples=[]
        for i in range(40):
            r=candidate("P"+str(i))
            r.update(date=f"2026-01-{i%20+1:02d}",result_hr=int(i%4==0))
            samples.append(r)
        result=posterior.evidence(row,pd.DataFrame(samples),config.Config())
        self.assertEqual(result["historical_bets"],40)
        self.assertEqual(result["peer_bets"],0)
        self.assertEqual(result["historical_hr"],10)

    def test_decision_gates_before_sizing(self):
        row=strong()
        self.assertEqual(decisions.classify(row,config.Config())[0],"BET")
        for field,value,reason in [("historical_bets",2,"SMALL_SAMPLE"),("p_positive_ev",.6,"UNCERTAINTY_HIGH"),
                                   ("lineup_status","not_confirmed","LINEUP_UNCONFIRMED")]:
            r={**row,field:value}
            decision,reasons=decisions.classify(r,config.Config())
            self.assertNotEqual(decision,"BET")
            self.assertIn(reason,reasons)
        r={**row,"odds_observed":"2020-01-01T00:00:00+00:00"}
        self.assertIn("STALE_PRICE",decisions.classify(r,config.Config())[1])

    def test_portfolio_caps_and_recorded_positions(self):
        c=config.Config(max_stake=1,max_daily=2,max_game=1.5,max_team=1.5,max_family=1.5,max_model=1.5)
        rows=decisions.allocate([strong("A"),strong("B"),strong("C")],c,100)
        self.assertLessEqual(sum(r["recommended_units"] for r in rows),1.5)
        self.assertLessEqual(max(r["recommended_units"] for r in rows),1)
        self.assertTrue(all(r["decision"]=="BET" for r in rows))
        self.assertEqual([r["recommended_units"] for r in rows], [.5, .5, .5])
        already=strong("A")
        already["actual_units_bet"]=1
        new=decisions.allocate([strong("A"),strong("B")],c,100,[already])
        self.assertEqual(new[0]["recommended_units"],0)
        self.assertLessEqual(new[1]["recommended_units"],.5)

    def test_hhi_uses_allocated_not_duplicated_family_exposure(self):
        r=strong()
        r["recommended_units"]=1
        e=metrics.exposure([r])
        family=e[e.dimension.eq("Signal family")]
        self.assertAlmostEqual(family.allocated_units.sum(),1)
        self.assertAlmostEqual(family.hhi.sum(),1/len(r["signal_families"]))

    def test_meta_offset_zero_coefficients_equals_market(self):
        f=pd.DataFrame([candidate()])
        model=dict(coefficients=[0]*len(meta_model.FEATURES))
        self.assertAlmostEqual(meta_model.predict(model,f)[0],1/6)

    def test_meta_validation_never_trains_on_evaluation_dates(self):
        rng=np.random.default_rng(2)
        rows=[]
        for i in range(240):
            r=candidate("P"+str(i),american_odds=500+(i%3)*50)
            r.update(date=(date(2025,1,1)+timedelta(days=i//4)).isoformat(),result_hr=int(rng.random()<.2))
            rows.append(r)
        m=meta_model.train(pd.DataFrame(rows),config.Config(min_train=80,min_oos=20))
        self.assertTrue(m["oos_predictions"])
        self.assertTrue(all(r["trained_through"]<r["date"] for r in m["oos_predictions"]))


class FinancialLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_capture_is_not_an_actual_bet_and_first_cohort_is_frozen(self):
        first=history.capture(self.root,[strong()],"first")[0]
        changed=strong()
        changed["estimated_hr_probability"]=.4
        history.capture(self.root,[changed],"second")
        self.assertTrue(history.read(self.root,actual=True).empty)
        cohort=history.read(self.root)
        self.assertEqual(len(cohort),1)
        self.assertEqual(cohort.iloc[0].estimated_hr_probability,.3)
        self.assertEqual(cohort.iloc[0].snapshot_id,first["snapshot_id"])

    def test_record_idempotency_and_actual_stakes(self):
        row=history.capture(self.root,[strong()],"first")[0]
        history.record(self.root,row["snapshot_id"],.4,550)
        self.assertEqual(history.read(self.root,True).iloc[0].actual_units_bet,.4)
        with self.assertRaises(ValueError): history.record(self.root,row["snapshot_id"],.4,550)
        history.remove_record(self.root,history.identity(row))
        self.assertTrue(history.read(self.root,True).empty)

    def test_no_backfill_into_forward_cohort(self):
        r=strong(start_time="2020-01-01T00:00:00+00:00")
        history.capture(self.root,[r],"old")
        self.assertTrue(history.read(self.root).empty)

    def test_settlement_missing_data_stays_pending_and_hit_uses_actual_odds(self):
        r=history.capture(self.root,[strong()],"run")[0]
        history.record(self.root,r["snapshot_id"],.4,550)
        results=self.root/"results"
        results.mkdir()
        schedule=lambda day:{"dates":[{"games":[{"gamePk":1,"status":{"abstractGameState":"Final"}}]}]}
        pd.DataFrame([dict(game_id="1",player_id="other",actual_hr=0,actual_pa=4)]).to_csv(results/f"daily_results_{r['date']}.csv",index=False)
        history.settle(self.root,results,r["date"],schedule)
        self.assertEqual(history.read(self.root,True).iloc[0].result,"Pending")
        pd.DataFrame([dict(game_id="1",player_id="10",actual_hr=1,actual_pa=4,actual_ab=4,is_starter=True)]).to_csv(results/f"daily_results_{r['date']}.csv",index=False)
        history.settle(self.root,results,r["date"],schedule)
        settled=history.read(self.root,True).iloc[0]
        self.assertEqual(settled.result,"HR")
        self.assertAlmostEqual(settled.profit_units,2.2)

    def test_drawdown_includes_starting_bankroll_and_roi_is_stake_weighted(self):
        rows=[]
        for i,(result,units) in enumerate([(0,1),(0,2),(1,.5)]):
            r=strong("P"+str(i))
            r.update(recommended_units=units,result_hr=result,result="HR" if result else "No HR",recorded=str(i),actual_units_bet=0)
            rows.append(r)
        f=metrics.strategy(pd.DataFrame(rows))
        summary=metrics.summary(f,100)
        self.assertAlmostEqual(summary["max_drawdown"],3)
        self.assertAlmostEqual(summary["profit"],-.5)
        self.assertAlmostEqual(summary["roi"],-.5/3.5*100)
        self.assertTrue(metrics.timeline(f,100,20).rolling_roi.isna().all())


    def test_expired_recommendations_refresh_once(self):
        row=strong()
        self.assertFalse(decisions.needs_refresh([row],config.Config()))
        row["odds_observed"]="2020-01-01T00:00:00+00:00"
        self.assertTrue(decisions.needs_refresh([row],config.Config()))
        row["decision"],row["reasons"]=decisions.classify(row,config.Config())
        self.assertFalse(decisions.needs_refresh([row],config.Config()))
        row["start_time"]=None
        self.assertIn("GAME_TIME_UNKNOWN",decisions.classify(row,config.Config())[1])

    def test_voids_and_unfinished_games(self):
        r=history.capture(self.root,[strong()],"run")[0]
        history.record(self.root,r["snapshot_id"],.4,550)
        results=self.root/"results"
        results.mkdir()
        final=lambda day:{"dates":[{"games":[{"gamePk":1,"status":{"abstractGameState":"Final"}}]}]}
        live=lambda day:{"dates":[{"games":[{"gamePk":1,"status":{"abstractGameState":"Live"}}]}]}
        for fields in [dict(actual_pa=0,actual_ab=0,lineup_position=""),
                       dict(actual_pa=1,actual_ab=1,lineup_position="PH")]:
            pd.DataFrame([dict(game_id="1",player_id="10",actual_hr=0,**fields)]).to_csv(results/f"daily_results_{r['date']}.csv",index=False)
            with history.database(self.root) as db:
                db.execute("DELETE FROM outcomes")
            history.settle(self.root,results,r["date"],live)
            self.assertEqual(history.read(self.root,True).iloc[0].result,"Pending")
            history.settle(self.root,results,r["date"],final)
            settled=history.read(self.root,True)
            self.assertEqual(settled.iloc[0].result,"Void")
            self.assertEqual(settled.iloc[0].profit_units,0)
            self.assertEqual(metrics.summary(metrics.strategy(settled,"actual"))["bets"],0)

    def test_export_matches_simulated_chart_and_not_actual_ledger(self):
        row=history.capture(self.root,[dict(strong(),recommended_units=.4)],"run")[0]
        with history.database(self.root) as db:
            db.execute("INSERT INTO outcomes VALUES(?,?,?,?)",("1","10","HR","now"))
        raw=history.read(self.root)
        export=metrics.history_export(raw,"sized",100)
        self.assertAlmostEqual(export.iloc[0].profit,2)
        self.assertAlmostEqual(export.iloc[0].bankroll_after,102)
        self.assertEqual(export.iloc[0].actual_units_bet,0)
        self.assertTrue(pd.isna(export.iloc[0].profit_units))
        self.assertEqual(json.loads(export.iloc[0].signal_labels),row["signal_labels"])

    def test_actual_price_changes_ev_and_confidence(self):
        r=history.capture(self.root,[dict(strong(),recommended_units=1)],"run")[0]
        history.record(self.root,r["snapshot_id"],.4,100)
        f=metrics.strategy(history.read(self.root,True),"actual")
        self.assertAlmostEqual(f.iloc[0].q,.5)
        self.assertAlmostEqual(f.iloc[0].ev,-.4)
        self.assertLess(f.iloc[0].p_positive_ev,.01)

    def test_empty_inputs_are_supported(self):
        rows,model=engine.synthesize(pd.DataFrame(),pd.DataFrame(),config.Config())
        self.assertEqual(rows,[])
        self.assertFalse(model["gate_passed"])
        self.assertTrue(metrics.history_export(pd.DataFrame(),"sized",100).empty)


if __name__=="__main__":
    unittest.main()
