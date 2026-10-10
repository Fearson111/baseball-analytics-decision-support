from pathlib import Path
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from all_seeing_eye.daily_hub.history import parlay_profit_timeline


ROWS = [
    dict(game_date="2026-09-03", signal="active_2leg", result="HIT", profit_1u=9.),
    dict(game_date="2026-09-01", signal="active_movement", result="MISS", profit_1u=-1.),
    dict(game_date="2026-09-03", signal="active_movement", result="MISS", profit_1u=-1.),
    dict(game_date="2026-09-02", signal="active_2leg", result="Pending", profit_1u=-99.),
    dict(game_date="2026-09-03", signal="active_4leg", result="Void", profit_1u=99.),
]


def parlay_app(rows):
    from pathlib import Path
    from unittest.mock import patch
    import pandas as pd
    import streamlit as st
    from all_seeing_eye.daily_hub import history

    def capture(chart, **kwargs):
        st.session_state["chart_data"] = chart.data.to_dict("records")
        st.session_state["chart_spec"] = chart.to_dict()
        st.caption("Chart placeholder")
    with patch("all_seeing_eye.profit_lens_app.build_parlay_history_frame", return_value=pd.DataFrame()), \
            patch.object(history.ledger, "first_day", return_value=None), \
            patch.object(history.ledger, "history", return_value=pd.DataFrame(rows)), \
            patch.object(st, "altair_chart", capture):
        history.render_parlay_history(Path("/unused"))


class ParlayHistoryChartTests(unittest.TestCase):
    def test_combines_groups_by_date_before_accumulating(self):
        timeline = parlay_profit_timeline(pd.DataFrame(ROWS))
        self.assertEqual(timeline.game_date.dt.strftime("%Y-%m-%d").tolist(), ["2026-09-01", "2026-09-03"])
        self.assertEqual(timeline.daily_profit_1u.tolist(), [-1., 8.])
        self.assertEqual(timeline.running_profit_1u.tolist(), [-1., 7.])
        self.assertEqual(timeline.tickets.tolist(), [1, 2])

    def test_empty_and_unsettled_history_have_no_profit_curve(self):
        self.assertTrue(parlay_profit_timeline(pd.DataFrame()).empty)
        self.assertTrue(parlay_profit_timeline(pd.DataFrame(ROWS[3:])).empty)

    def test_default_is_single_combined_line_and_group_filter_updates_it(self):
        app = AppTest.from_function(parlay_app, args=(ROWS,)).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value, "All")
        self.assertEqual(app.session_state["chart_data"][-1]["running_profit_1u"], 7.)
        self.assertEqual(app.session_state["chart_spec"]["mark"]["type"], "line")
        self.assertNotIn("color", app.session_state["chart_spec"]["encoding"])
        self.assertEqual(app.metric[2].value, "+7.00u")
        app.selectbox[0].select("active_2leg").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["chart_data"][-1]["running_profit_1u"], 9.)
        self.assertEqual(app.metric[2].value, "+9.00u")
        app.selectbox[0].select("active_4leg").run()
        self.assertEqual(app.info[0].value, "No settled parlay results for this selection yet.")


if __name__ == "__main__":
    unittest.main()
