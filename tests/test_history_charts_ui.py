import unittest

from streamlit.testing.v1 import AppTest


def history_app(settled):
    from unittest.mock import patch
    import pandas as pd
    import streamlit as st
    from all_seeing_eye.financial_system import page
    from all_seeing_eye.financial_system.config import Config

    empty = pd.DataFrame()
    timeline = pd.DataFrame([dict(date="2026-09-11", stake=1., bankroll_before=100.)]) if settled else empty
    summary = dict(bets=1, hr=1, units_risked=1., profit=5., roi=500., max_drawdown=0.,
                   current_bankroll=105., expected_profit=.3)
    def chart(frame, x, series, title, *args, **kwargs):
        st.subheader(title)
    with patch.object(page.metrics, "strategy", return_value=empty), \
            patch.object(page.metrics, "summary", return_value=summary), \
            patch.object(page.metrics, "timeline", return_value=timeline), \
            patch.object(page.charts, "lines", chart):
        page.history_charts((empty, empty), Config())


class HistoryChartsUITests(unittest.TestCase):
    def test_history_keeps_six_summary_metrics_without_bankroll_or_expected_profit(self):
        for settled in (False, True):
            with self.subTest(settled=settled):
                app = AppTest.from_function(history_app, args=(settled,)).run()
                self.assertFalse(app.exception)
                self.assertEqual([m.label for m in app.metric], [
                    "Bets", "HR", "Units risked", "Profit / loss", "ROI %", "Max drawdown %"])
                self.assertNotIn("Bankroll curve", [h.value for h in app.subheader])
                if settled:
                    self.assertCountEqual([h.value for h in app.subheader][1:], [
                        "Equity: realized vs expected", "Drawdown", "Rolling ROI",
                        "Actual vs expected home runs", "Probability residuals", "Return residual",
                        "Stake and exposure history"])


if __name__ == "__main__":
    unittest.main()
