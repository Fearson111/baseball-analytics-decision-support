import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from all_seeing_eye.financial_system import charts, metrics


def position(player, game="1", stake=1., **changes):
    row = dict(player=player, player_key=player.lower(), game_id=game, team="HOU", opponent="ARI",
               start_time="2026-09-06T20:00:00Z", recommended_units=stake, actual_units_bet=stake,
               signal_families=["eye", "market_edge"], model_families=["Eye", "GBM"],
               price_bucket="+300 to <+400", result="Pending")
    row.update(changes)
    return row


def render_exposure(rows, actual, dimension, historical=False):
    from all_seeing_eye.financial_system.page import exposure_view
    exposure_view(rows, actual, dimension=dimension, historical=historical)


def render_live_exposure():
    from pathlib import Path
    from all_seeing_eye.financial_system.page import current_exposure_view
    from all_seeing_eye.financial_system.config import Config
    current_exposure_view(Path("/unused"), "2026-09-11", Config(max_daily=4.), "Game")


def render_live_monitor():
    from datetime import date
    from pathlib import Path
    import streamlit as st
    from all_seeing_eye.financial_system.page import live_result_monitor
    live_result_monitor(Path("/unused"), date.today().isoformat())
    st.write("Financial history refreshed")


class PortfolioDisplayTests(unittest.TestCase):
    def test_partial_roi_identifies_missing_player_and_keeps_all_bars(self):
        recorded = [position("Luis Garcia", stake=.5, estimated_hr_probability=.25, actual_american_odds=500),
                    position("CJ Abrams", stake=.5, estimated_hr_probability=None, actual_american_odds=620)]
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=([], recorded, "Game")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any(item.label == "Expected ROI (modeled)" and item.value == "+50.00%" for item in app.metric))
        self.assertTrue(any("1 of 2 positions (0.50u of 1.00u)" in item.value and "CJ Abrams" in item.value
                            for item in app.expander[0].caption))
        self.assertTrue(any("2 unsettled wagers (1.00u)" in item.value for item in app.caption))
        self.assertEqual(set(render.call_args.args[0].player), {"Luis Garcia", "CJ Abrams"})

    def test_settled_daily_summary_uses_realized_results_not_model_coverage(self):
        recorded = [position("Matt Olson", stake=1.5, actual_american_odds=375, result="HR"),
                    position("Other wagers", stake=2.5, actual_american_odds=500, result="No HR")]
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=([], recorded, "Game")).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("All wagers settled" in c.value and "Net P/L: +3.13u" in c.value
                            and "Realized ROI: +78.13%" in c.value for c in app.caption))
        render.assert_not_called()

    def test_partial_settlement_does_not_call_roi_final_or_count_pending_as_losses(self):
        rows = [position("Olson", stake=1.5, result="HR", actual_american_odds=375),
                position("Pending", stake=2.5, actual_american_odds=500)]
        result = metrics.portfolio_settlement_summary(rows)
        self.assertEqual(result["pending_units"], 2.5)
        self.assertEqual(result["profit"], 5.625)
        self.assertEqual(result["roi"], 375)
        with patch.object(charts, "player_exposure"):
            app = AppTest.from_function(render_exposure, args=([], rows, "Game")).run()
        self.assertTrue(any("ROI on settled wagers: +375.00%" in c.value for c in app.caption))

    def test_void_stake_does_not_enter_realized_roi(self):
        rows = [position("Winner", result="HR", actual_american_odds=300),
                position("Void", stake=2, result="Void")]
        result = metrics.portfolio_settlement_summary(rows)
        self.assertEqual(result["recorded_units"], 3)
        self.assertEqual(result["roi"], 300)
        self.assertEqual(result["void_count"], 1)

    def test_live_exposure_rereads_ledger_after_settlement(self):
        from all_seeing_eye.financial_system import history
        rows = [position("Olson", stake=1.5, date="2026-09-11", actual_american_odds=375)]
        app = AppTest.from_function(render_live_exposure)
        with patch.object(history, "read", return_value=pd.DataFrame(rows)), patch.object(charts, "player_exposure"):
            app.run()
        self.assertTrue(any("1 unsettled wager" in c.value for c in app.caption))
        rows[0]["result"] = "HR"
        with patch.object(history, "read", return_value=pd.DataFrame(rows)), patch.object(charts, "player_exposure") as chart:
            app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("All wagers settled" in c.value for c in app.caption))
        self.assertFalse(any("unsettled wager" in c.value for c in app.caption))
        chart.assert_not_called()

    def test_live_result_change_reruns_whole_page_for_history(self):
        from all_seeing_eye.financial_system import results
        report = dict(newly_graded=1, corrected=0, finalized=0, tracked_players=1,
                      checked_at="2026-09-12T01:00:00+00:00", errors=[])
        with patch.object(results, "scan_day", side_effect=[report, {**report, "newly_graded":0}]) as scan:
            app = AppTest.from_function(render_live_monitor).run()
        self.assertFalse(app.exception)
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(scan.call_args.kwargs, dict(include_live=True, recorded_only=True, min_interval_seconds=30))
        self.assertTrue(any("Financial history refreshed" in m.value for m in app.markdown))

    def test_provisional_live_win_is_not_presented_as_final_roi(self):
        rows = [position("Olson", stake=1.5, result="HR", actual_american_odds=375, result_provisional=True)]
        app = AppTest.from_function(render_exposure, args=([], rows, "Game")).run()
        text = " ".join(c.value for c in app.caption)
        self.assertIn("P/L including live HR: +5.63u", text)
        self.assertIn("awaiting final confirmation", text)
        self.assertNotIn("All wagers settled", text)
        self.assertNotIn("Realized ROI", text)

    def test_current_portfolio_excludes_unrecorded_recommendations(self):
        recommended = [position("Michael Busch", stake=.5)]
        recorded = [position("Jose Ramirez"), position("Matt Olson", stake=1.5)]
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=(recommended, recorded, "Game")).run()
        self.assertEqual(len(app.exception), 0)
        segments = render.call_args.args[0]
        self.assertEqual(set(segments.player), {"Jose Ramirez", "Matt Olson"})
        self.assertEqual(set(segments.source), {"Recorded"})
        self.assertEqual(segments.units.sum(), 2.5)

    def test_recommendation_alone_does_not_create_current_portfolio(self):
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=([position("Michael Busch")], [], "Game")).run()
        self.assertEqual(len(app.exception), 0)
        render.assert_not_called()
        self.assertEqual(app.info[0].value, "No active exposure on this slate.")

    def test_explicit_frozen_recommendation_view_still_renders(self):
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=([position("Michael Busch")], [], "Game", True)).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(render.call_args.args[0].player.tolist(), ["Michael Busch"])
        self.assertEqual(render.call_args.args[0].source.tolist(), ["Recommended"])

    def test_single_recorded_position_keeps_colored_player_chart(self):
        recorded = position("Jose Ramirez", team="CLE", opponent="MIN")
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=([], [recorded], "Team")).run()
        self.assertEqual(len(app.exception), 0)
        render.assert_called_once()
        segments = render.call_args.args[0]
        self.assertEqual(segments.player.tolist(), ["Jose Ramirez"])
        self.assertEqual(segments.team.tolist(), ["CLE"])
        self.assertEqual(segments.group.tolist(), ["CLE"])
        self.assertEqual(segments.units.tolist(), [1.])

    def test_portfolio_metrics_hide_redundant_stake_and_cap_but_keep_budget_math(self):
        from all_seeing_eye.financial_system import history
        rows = [position("Kevin McGonigle", stake=1., date="2026-09-11",
                         estimated_hr_probability=.25, actual_american_odds=747)]
        with patch.object(history, "read", return_value=pd.DataFrame(rows)), patch.object(charts, "player_exposure"):
            app = AppTest.from_function(render_live_exposure).run()
        self.assertFalse(app.exception)
        values = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(values, {"Recorded stake": "1.00u", "Remaining budget": "3.00u", "Expected ROI": "+111.75%"})
        self.assertEqual(len(app.metric), 3)
        columns = app.get("column")[:3]
        self.assertEqual([column.metric[0].label for column in columns],
                         ["Recorded stake", "Remaining budget", "Expected ROI"])
        self.assertEqual(len({column.proto.weight for column in columns}), 1)

    def test_three_summary_metrics_remain_for_empty_and_multiple_positions(self):
        from all_seeing_eye.financial_system import history
        for count in (0, 2):
            with self.subTest(count=count):
                rows = [position(f"Player {i}", date="2026-09-11",
                                 estimated_hr_probability=.25, actual_american_odds=500)
                        for i in range(count)]
                with patch.object(history, "read", return_value=pd.DataFrame(rows)), patch.object(charts, "player_exposure"):
                    app = AppTest.from_function(render_live_exposure).run()
                self.assertFalse(app.exception)
                self.assertEqual(len(app.metric), 3)
                self.assertEqual([column.metric[0].label for column in app.get("column")[:3]],
                                 ["Recorded stake", "Remaining budget", "Expected ROI"])
                self.assertEqual(app.metric[2].value, "+50.00%" if count else "Not available")

    def test_over_cap_recorded_stakes_are_not_changed_by_display_cleanup(self):
        from all_seeing_eye.financial_system import history
        rows = [position("Recorded", stake=5., date="2026-09-11", actual_american_odds=400)]
        with patch.object(history, "read", return_value=pd.DataFrame(rows)), patch.object(charts, "player_exposure"):
            app = AppTest.from_function(render_live_exposure).run()
        self.assertFalse(app.exception)
        values = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(values["Recorded stake"], "5.00u")
        self.assertEqual(values["Remaining budget"], "0.00u")
        self.assertNotIn("Allocated stake", values)
        self.assertNotIn("Daily cap", values)

    def test_multiple_positions_still_render_grouped_player_chart(self):
        recorded = [position("Harper", team="PHI"), position("Lindor", team="NYM")]
        with patch.object(charts, "player_exposure") as render:
            app = AppTest.from_function(render_exposure, args=([], recorded, "Game")).run()
        self.assertEqual(len(app.exception), 0)
        render.assert_called_once()
        self.assertEqual(len(render.call_args.args[0]), 2)
        self.assertEqual(render.call_args.args[0].units.sum(), 2.)

    def test_recorded_position_replaces_recommendation(self):
        rows = metrics.portfolio_positions([position("Yordan")], [position("Yordan", stake=.5)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exposure_units"], .5)
        self.assertEqual(rows[0]["position_source"], "Recorded")

    def test_only_pending_wagers_remain_active(self):
        settled = position("Yordan", result="HR")
        self.assertEqual(metrics.portfolio_positions([position("Yordan")], [settled]), [])
        self.assertEqual(len(metrics.portfolio_positions([], [settled], historical=True)), 1)

    def test_watch_zero_stakes_do_not_count_as_active(self):
        rows = metrics.portfolio_positions([position("Yordan"), position("Rice", stake=0)])
        self.assertEqual(len(rows), 1)

    def test_matchup_names_group_opposing_team_players(self):
        rows = metrics.portfolio_positions([position("Yordan", stake=.5),
                                            position("Carroll", stake=1.5, team="ARI", opponent="HOU")])
        f = metrics.exposure_segments(rows)
        self.assertEqual(f.group.nunique(), 1)
        self.assertEqual(f.group.iloc[0], "HOU vs ARI")
        self.assertAlmostEqual(f.units.sum(), 2)
        self.assertEqual(set(f.units), {.5, 1.5})
        self.assertEqual(f.start.iloc[0], 0)
        self.assertEqual(f.end.iloc[-1], 2)
        self.assertEqual(f.start.iloc[1], f.end.iloc[0])

    def test_doubleheaders_remain_separate_named_bars(self):
        rows = [position("A"), position("B", game="2", start_time="2026-09-06T23:00:00Z")]
        labels = metrics.matchup_labels(rows)
        self.assertEqual(labels["1"], "HOU vs ARI / G1")
        self.assertEqual(labels["2"], "HOU vs ARI / G2")

    def test_family_segments_conserve_allocated_stake(self):
        rows = metrics.portfolio_positions([position("A"), position("B")])
        f = metrics.exposure_segments(rows, "Signal family")
        self.assertAlmostEqual(f.units.sum(), 2)
        self.assertEqual(set(f.units), {.5})

    def test_player_segment_chart_spec_is_valid(self):
        f = metrics.exposure_segments(metrics.portfolio_positions([position("A"), position("B")]))
        with patch.object(charts.st, "altair_chart") as render:
            charts.player_exposure(f)
        spec = render.call_args.args[0].to_dict()
        self.assertEqual(spec["height"], {"step": 52})
        self.assertEqual(spec["layer"][0]["mark"]["size"], 40)
        for layer in spec["layer"]:
            self.assertIsNone(layer["encoding"]["x"]["axis"])
            self.assertIsNone(layer["encoding"]["y"]["axis"])
        records = next(iter(spec["datasets"].values()))
        self.assertTrue(all(r["team_color"] == "#EB6E1F" for r in records))
        self.assertIn("scale('x'", spec["layer"][1]["mark"]["limit"]["expr"])

    def test_team_colors_and_contrast_follow_each_player(self):
        rows = metrics.portfolio_positions([
            position("Harper", team="PHI"), position("Lindor", game="2", team="NYM"),
            position("Unknown", game="3", team="UNKNOWN")])
        f = metrics.exposure_segments(rows)
        with patch.object(charts.st, "altair_chart") as render:
            charts.player_exposure(f)
        records = next(iter(render.call_args.args[0].to_dict()["datasets"].values()))
        by_name = {r["player"]: r for r in records}
        self.assertEqual(by_name["Harper"]["team_color"], "#E81828")
        self.assertEqual(by_name["Lindor"]["team_color"], "#002D72")
        self.assertEqual(by_name["Unknown"]["team_color"], "#61646A")
        self.assertTrue(all(r["text_color"] == "#FFFFFF" for r in records))
        self.assertEqual(by_name["Harper"]["label"], "Harper  1.00u")

    def test_player_bar_uses_recorded_boosted_odds_and_signed_prices(self):
        recorded = [position("Luis Garcia", stake=.5, actual_american_odds=500, american_odds=385),
                    position("Other Player", game="2", actual_american_odds=-110, american_odds=500)]
        segments = metrics.exposure_segments(metrics.portfolio_positions([], recorded))
        with patch.object(charts.st, "altair_chart") as render:
            charts.player_exposure(segments)
        spec = render.call_args.args[0].to_dict()
        records = next(iter(spec["datasets"].values()))
        by_name = {r["player"]: r for r in records}
        self.assertEqual(by_name["Luis Garcia"]["label"], "Luis Garcia  0.50u  +500")
        self.assertEqual(by_name["Luis Garcia"]["stake_odds"], "0.50u +500")
        self.assertEqual(by_name["Other Player"]["label"], "Other Player  1.00u  -110")
        self.assertTrue(any(t["title"] == "Book odds" for t in spec["layer"][0]["encoding"]["tooltip"]))

    def test_recommendation_bar_uses_recommended_odds(self):
        segments = metrics.exposure_segments(metrics.portfolio_positions([
            position("Recommended", american_odds=550, actual_american_odds=500)]))
        self.assertEqual(segments.american_odds.tolist(), [550])

    def test_calendar_curve_uses_stakes_and_excludes_pending_voids(self):
        frame = pd.DataFrame([
            dict(date="2026-09-01", result="No HR", profit=-2., expected_profit=.4, return_1u=-1., stake=2.),
            dict(date="2026-09-03", result="HR", profit=2.5, expected_profit=.1, return_1u=5., stake=.5),
            dict(date="2026-09-03", result="No HR", profit=-.25, expected_profit=.05, return_1u=-1., stake=.25),
            dict(date="2026-09-04", result="Pending", profit=99., expected_profit=99., return_1u=99., stake=99.),
            dict(date="2026-09-04", result="Void", profit=0., expected_profit=99., return_1u=0., stake=99.),
        ])
        f = metrics.portfolio_curve(frame)
        self.assertEqual(len(f), 4)
        self.assertEqual(f.date.iloc[0], pd.Timestamp("2026-08-31"))
        self.assertEqual(f.realized.tolist(), [0, -2, -2, .25])
        self.assertEqual(f.flat.iloc[-1], 3.)
        self.assertAlmostEqual(f.expected.iloc[-1], .55)
        self.assertAlmostEqual(f.residual.iloc[-1], -.3)
        self.assertEqual(f.drawdown.tolist(), [0, -2, -2, 0])
        self.assertEqual(f.peak.iloc[-1], .25)

    def test_no_fake_history_when_only_pending(self):
        self.assertTrue(metrics.portfolio_curve(pd.DataFrame()).empty)
        self.assertTrue(metrics.portfolio_curve(pd.DataFrame([dict(result="Pending")])).empty)

    def test_selected_reference_lines_only(self):
        f = pd.DataFrame([dict(date="2026-09-01", realized=1., expected=.2, baseline=0.)])
        with patch.object(charts.st, "altair_chart") as render:
            charts.portfolio_history(f, {"realized": "Realized P/L", "baseline": "Break-even"})
        spec = render.call_args.args[0].to_dict()
        records = next(iter(spec["datasets"].values()))
        self.assertEqual({r["Series"] for r in records}, {"Realized P/L", "Break-even"})


if __name__ == "__main__":
    unittest.main()
