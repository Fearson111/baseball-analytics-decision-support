import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from all_seeing_eye import sequence_edge, profit_lens_app
from all_seeing_eye.edge_buckets import edge_bucket_signals, signal_rows
from all_seeing_eye.retired_signals import RETIRED_SIGNALS, without_retired_signals
from all_seeing_eye.table_display import display_frame, display_value, table_data_and_config
from all_seeing_eye.daily_hub.presentation import display_value as posting_value


class RetiredSignalTests(unittest.TestCase):
    def test_rule_registries_exclude_all_four(self):
        titles = {rule.title for rule in edge_bucket_signals()}
        titles.update(rule["signal"] for rule in sequence_edge.SIGNAL_RULES)
        self.assertFalse(titles & RETIRED_SIGNALS)
        self.assertEqual(len(edge_bucket_signals()), 5)
        self.assertEqual(len(sequence_edge.SIGNAL_RULES), 5)
        self.assertEqual(signal_rows([{"model_top25_rank": 1, "edge_percent": -7, "book_american_odds": 350}]), [])

    def test_saved_frames_filtered_without_mutating_snapshot(self):
        source = pd.DataFrame({"signal": list(RETIRED_SIGNALS) + ["Premium Signal"], "value": range(5)})
        before = source.copy()
        filtered = without_retired_signals(source)
        self.assertEqual(filtered.signal.tolist(), ["Premium Signal"])
        pd.testing.assert_frame_equal(source, before)
        pd.testing.assert_frame_equal(without_retired_signals(pd.DataFrame()), pd.DataFrame())

    def test_saved_sequence_active_cannot_restore_retired_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026-09-04"
            day.mkdir()
            pd.DataFrame({"signal": list(RETIRED_SIGNALS) + [sequence_edge.SIGNAL_401_500]}).to_csv(day / "sequence_active.csv", index=False)
            with patch.object(sequence_edge, "historical_signal_rows", return_value=pd.DataFrame()):
                active, _, summary = sequence_edge.build_sequence_edge_frames(Path(tmp), day)
            self.assertEqual(active.signal.tolist(), [sequence_edge.SIGNAL_401_500])
            self.assertFalse(set(summary.signal) & RETIRED_SIGNALS)

    def test_sequence_active_and_history_do_not_emit_retired_rules(self):
        joined = pd.DataFrame([{
            "player": "Test Player", "game_date": "2026-09-04", "eye_rank": 1,
            "gbm_rank": 1, "sequence_projection_rank": 1, "book_american_odds": 350,
            "edge_percent": -7, "has_5_step_motif": True, "has_contact_quality_note": True,
            "has_high_lift_5_step": True,
        }])
        with patch.object(sequence_edge, "load_sequence_projection", return_value=joined), \
             patch.object(sequence_edge, "load_sequence_history", return_value=joined), \
             patch.object(sequence_edge, "load_board", return_value=pd.DataFrame()), \
             patch.object(sequence_edge, "load_all_boards", return_value=pd.DataFrame()), \
             patch.object(sequence_edge, "join_sequence_to_board", return_value=joined), \
             patch.object(sequence_edge, "active_dedup_bucket_high_lift_rows", return_value=pd.DataFrame()), \
             patch.object(sequence_edge, "historical_dedup_bucket_high_lift_rows", return_value=pd.DataFrame()), \
             patch.object(sequence_edge, "normalize_output", side_effect=lambda frame, **kwargs: frame):
            active = sequence_edge.active_signal_rows(Path("."), "2026-09-04")
            history = sequence_edge.historical_signal_rows(Path("."))
        self.assertFalse(set(active.signal) & RETIRED_SIGNALS)
        self.assertFalse(set(history.signal) & RETIRED_SIGNALS)
        self.assertEqual(len(active), 3)

    def test_frozen_ledger_history_also_excludes_retired_signals(self):
        from all_seeing_eye.daily_hub import history
        frozen = pd.DataFrame({"signal": list(RETIRED_SIGNALS) + ["Premium Signal"]})
        with patch.object(profit_lens_app, "build_history_frame", return_value=pd.DataFrame()), \
             patch.object(profit_lens_app, "build_regression_misprice_history_frame", return_value=pd.DataFrame()), \
             patch("all_seeing_eye.edge_buckets.build_edge_bucket_history_rows", return_value=[]), \
             patch.object(sequence_edge, "historical_signal_rows", return_value=pd.DataFrame()), \
             patch.object(history.ledger, "first_day", return_value=None), \
             patch.object(history.ledger, "history", return_value=frozen):
            result = history.straight_history(Path("."))
        self.assertEqual(result.signal.tolist(), ["Premium Signal"])


class TablePrecisionTests(unittest.TestCase):
    def test_numeric_strings_percentages_and_financial_exceptions(self):
        self.assertEqual(display_value("18.56789", "model_hr%"), "18.6")
        self.assertEqual(display_value("-2.567%", "edge"), "-2.6%")
        self.assertEqual(display_value("51.3456x", "parlay"), "51.3x")
        self.assertEqual(display_value("61.718%", "ROI"), "61.72%")
        self.assertEqual(display_value(10.499, "running_profit_1u"), "10.50")
        self.assertEqual(display_value("+3.456u"), "+3.46u")
        self.assertEqual(display_value(0, "profit_units"), "0.00")
        self.assertEqual(display_value("+450", "odds"), "+450")
        self.assertEqual(display_value("2026-09-04", "date"), "2026-09-04")
        self.assertEqual(display_value(pd.NA), "")
        self.assertEqual(display_value("Model Rank 1-5 / Edge 2.5-5%", "signal"), "Model Rank 1-5 / Edge 2.5-5%")

    def test_streamlit_keeps_full_numeric_data_but_limits_format(self):
        source = pd.DataFrame({"score": [18.56789], "roi_percent": [31.789], "rank": [1], "edge": ["1.2345"]})
        original = source.copy()
        config = {"score": {"label": "Score", "type_config": {"type": "number", "format": "%.4f"}}}
        result, settings = table_data_and_config(source, config)
        self.assertEqual(result.score.iloc[0], 18.56789)
        self.assertEqual(settings["score"]["type_config"]["format"], "%.1f")
        self.assertEqual(settings["roi_percent"]["type_config"]["format"], "%.2f")
        self.assertEqual(result.edge.iloc[0], "1.2")
        self.assertEqual(config["score"]["type_config"]["format"], "%.4f")
        pd.testing.assert_frame_equal(source, original)

    def test_posting_and_native_tables_share_precision(self):
        for column in ["edge%", "model_hr%", "regr_score", "unknown_numeric"]:
            self.assertEqual(posting_value("18.56789", column), "18.6")
        frame = pd.DataFrame({"score": [18.56789], "profit_1u": [10.499]})
        formatted = profit_lens_app.format_display_frame(frame)
        self.assertEqual(formatted.score.iloc[0], "18.6")
        self.assertEqual(formatted.profit_1u.iloc[0], "10.50")
        pd.testing.assert_frame_equal(formatted, display_frame(frame))


if __name__ == "__main__":
    unittest.main()
