import unittest

from all_seeing_eye.financial_system.metrics import portfolio_expected_roi, portfolio_positions, portfolio_roi_coverage


def position(stake, probability, odds, source="Recorded"):
    return dict(exposure_units=stake, estimated_hr_probability=probability,
                actual_american_odds=odds, american_odds=900,
                position_source=source)


class PortfolioExpectedRoiTests(unittest.TestCase):
    def test_total_is_stake_weighted_and_uses_actual_prices(self):
        rows = [position(1, .28, 400), position(.5, .2, 450)]
        # Expected profits are .40u and .05u, across 1.50u risked.
        self.assertAlmostEqual(portfolio_expected_roi(rows), 30)

    def test_recommended_position_uses_recommended_price(self):
        self.assertAlmostEqual(portfolio_expected_roi([position(1, .2, 450, "Recommended")]), 100)

    def test_incomplete_portfolio_is_not_reported_as_complete(self):
        for probability, odds in [(None, 450), (float("nan"), 450), (.2, None), (.2, 0), (1.1, 450)]:
            with self.subTest(probability=probability, odds=odds):
                self.assertIsNone(portfolio_expected_roi([position(1, .28, 400), position(.5, probability, odds)]))

    def test_no_positions(self):
        self.assertIsNone(portfolio_expected_roi([]))

    def test_boost_changes_payout_not_saved_probability(self):
        row = position(.5, .2741464721114041, 500)
        self.assertAlmostEqual(portfolio_expected_roi([row]), 64.48788326684246)
        row["actual_american_odds"] = 385
        self.assertLess(portfolio_expected_roi([row]), 64.48788326684246)
        self.assertEqual(row["estimated_hr_probability"], .2741464721114041)

    def test_partial_coverage_never_labels_subset_as_whole_portfolio(self):
        rows = [dict(position(1, .28, 400), player="Modeled"),
                dict(position(.5, None, 620), player="CJ Abrams")]
        coverage = portfolio_roi_coverage(rows)
        self.assertIsNone(coverage["roi"])
        self.assertAlmostEqual(coverage["modeled_roi"], 40)
        self.assertEqual(coverage["missing_players"], ["CJ Abrams"])
        self.assertEqual((coverage["modeled_units"], coverage["total_units"]), (1, 1.5))
        self.assertEqual((coverage["modeled_count"], coverage["total_count"]), (1, 2))

    def test_no_modeled_positions_does_not_invent_zero_roi(self):
        coverage = portfolio_roi_coverage([dict(position(.5, None, 500), player="Unmodeled")])
        self.assertIsNone(coverage["modeled_roi"])
        self.assertEqual(coverage["modeled_units"], 0)

    def test_only_active_positions_and_no_duplicate_recommendations(self):
        rows = [dict(position(1, .9, 450), player_key="a", recommended_units=1)]
        actual = [dict(position(.5, .2, 450), player_key="a", actual_units_bet=.5, result="Pending"),
                  dict(position(1, .8, 450), player_key="b", actual_units_bet=1, result="HR")]
        active = portfolio_positions(rows, actual)
        self.assertEqual(len(active), 1)
        self.assertAlmostEqual(portfolio_expected_roi(active), 10)
