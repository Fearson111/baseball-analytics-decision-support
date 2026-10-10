from copy import deepcopy
import unittest
import pandas as pd
from all_seeing_eye.table_display import sequence_table_data_and_config


class SequencePercentageDisplayTests(unittest.TestCase):
    def test_fractional_probability_display_and_source_preserved(self):
        source = pd.DataFrame({"hr_probability": [0.2034, 0, 1, None], "score": [2.123]*4})
        before = source.copy(deep=True)
        config = {"hr_probability": {"label": "HR probability", "type_config": {"type": "number", "format": "%.3f"}}}
        original = deepcopy(config)
        data, settings = sequence_table_data_and_config(source, config)
        self.assertAlmostEqual(data.hr_probability.iloc[0], 20.34)
        self.assertEqual(settings["hr_probability"]["type_config"]["format"] % data.hr_probability.iloc[0], "20.3%")
        self.assertEqual(data.hr_probability.iloc[2], 100)
        self.assertTrue(pd.isna(data.hr_probability.iloc[3]))
        self.assertEqual(settings["score"]["type_config"]["format"], "%.1f")
        pd.testing.assert_frame_equal(source, before)
        self.assertEqual(config, original)

    def test_summary_probabilities_and_string_input(self):
        data, config = sequence_table_data_and_config(pd.DataFrame({
            "avg_projected_probability": [0.156], "top_projected_probability": [0.229],
            "actual_hr_rate": [0.1], "hr_probability": ["0.164"]}))
        for column, expected in {"avg_projected_probability": 15.6, "top_projected_probability": 22.9,
                                 "actual_hr_rate": 10, "hr_probability": 16.4}.items():
            self.assertAlmostEqual(data[column].iloc[0], expected)
            self.assertEqual(config[column]["type_config"]["format"], "%.1f%%")


if __name__ == "__main__":
    unittest.main()
