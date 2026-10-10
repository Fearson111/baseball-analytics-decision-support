from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from all_seeing_eye.daily_hub.history import signal_history_table


ROWS = [
    dict(game_date="2026-09-12", player="Riley", signal="B", result="No HR", profit_1u=-1.),
    dict(game_date="2026-09-11", player="Ben", signal="A", result="HR", profit_1u=3.25),
    dict(game_date="2026-09-12", player="Riley", signal="A", result="No HR", profit_1u=-1.),
    dict(game_date="2026-09-12", player="Samuel", signal="A", result="Void", profit_1u=99.),
    dict(game_date="2026-09-13", player="Pending", signal="A", result="Pending", profit_1u=-99.),
]


def history_app(rows):
    from pathlib import Path
    from unittest.mock import patch
    import pandas as pd
    from all_seeing_eye.daily_hub import history

    with patch.object(history, "straight_history", return_value=pd.DataFrame(rows)):
        history.render_history(Path("/unused"))


class SignalHistoryTableTests(unittest.TestCase):
    def test_month_defaults_to_latest_and_preserves_all_time_running_profit(self):
        rows = ROWS + [dict(game_date="2026-08-31", player="Zoe", signal="A", result="HR", profit_1u=4.)]
        app = AppTest.from_function(history_app, args=(rows,)).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[1].value, "2026-09")
        self.assertEqual(app.selectbox[1].options, ["September 2026", "August 2026", "All months"])
        table = app.dataframe[0].value
        self.assertEqual(len(table), 5)
        self.assertTrue(table.game_date.str.startswith("2026-09").all())
        self.assertEqual(table.running_profit_1u.iloc[0], 5.25)
        app.selectbox[1].set_value("2026-08").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.game_date.tolist(), ["2026-08-31"])
        self.assertEqual(app.dataframe[0].value.running_profit_1u.tolist(), [4.])
        self.assertEqual(app.metric[2].value, "+5.25u")
        app.selectbox[1].select("All months").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 6)
        self.assertEqual(app.dataframe[0].value.game_date.iloc[0], "2026-09-13")
        app.selectbox[0].select("B").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[1].value, "2026-09")
        self.assertEqual(len(app.dataframe[0].value), 1)

    def test_newest_first_reverses_same_day_order_and_reconciles_each_row(self):
        source = pd.DataFrame(ROWS)
        original = source.copy(deep=True)
        view = signal_history_table(source)
        self.assertEqual(view.game_date.tolist(), ["2026-09-13"]+["2026-09-12"]*3+["2026-09-11"])
        self.assertEqual(view.player.tolist(), ["Pending", "Samuel", "Riley", "Riley", "Ben"])
        self.assertEqual(view.signal.tolist(), ["A", "A", "B", "A", "A"])
        np.testing.assert_allclose(view.running_profit_1u, [1.25, 1.25, 1.25, 2.25, 3.25])
        older_total = view.running_profit_1u.shift(-1, fill_value=0)
        np.testing.assert_allclose(view.running_profit_1u, older_total+view.profit_1u)
        pd.testing.assert_frame_equal(source, original)

    def test_selected_signal_restarts_its_own_cumulative_total(self):
        f = pd.DataFrame(ROWS)
        view = signal_history_table(f[f.signal.eq("B")])
        self.assertEqual(view.running_profit_1u.tolist(), [-1.])

    def test_empty_and_unsettled_rows_do_not_create_profit(self):
        f = pd.DataFrame(ROWS)
        self.assertTrue(signal_history_table(f.iloc[:0]).empty)
        view = signal_history_table(f[f.result.isin(["Void", "Pending"])])
        self.assertEqual(view.profit_1u.tolist(), [0., 0.])
        self.assertEqual(view.running_profit_1u.tolist(), [0., 0.])

    def test_ui_defaults_to_latest_first_with_visible_signals_and_numeric_profit(self):
        app = AppTest.from_function(history_app, args=(ROWS,)).run()
        self.assertFalse(app.exception)
        table = app.dataframe[0].value
        self.assertEqual(table.game_date.iloc[0], "2026-09-13")
        self.assertIn("signal", table.columns)
        self.assertTrue(pd.api.types.is_numeric_dtype(table.running_profit_1u))
        self.assertEqual(app.metric[2].value, "+1.25u")
        self.assertAlmostEqual(table.running_profit_1u.iloc[0], 1.25)
        app.selectbox[0].select("B").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.running_profit_1u.tolist(), [-1.])
        self.assertEqual(app.metric[2].value, "-1.00u")


if __name__ == "__main__":
    unittest.main()
