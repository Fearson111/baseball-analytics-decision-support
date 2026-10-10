import unittest
import pandas as pd

from all_seeing_eye.table_display import display_name, display_frame, table_data_and_config
from all_seeing_eye.daily_hub.presentation import posting_frame, table_html
from all_seeing_eye.profit_lens_app import format_display_frame, merge_visible_editor_changes, clean_export_text


class PlayerDisplayNameTests(unittest.TestCase):
    def test_name_variants(self):
        for name in ["Christian Encarnacion-Strand", "Christian Encarnacion Strand", "Christian Encarnación-Strand"]:
            self.assertEqual(display_name(name), "C. Encarnacion-Strand")
        self.assertEqual(display_name("Christian Walker"), "Christian Walker")

    def test_display_copies_preserve_identity(self):
        original = pd.DataFrame({"player": ["Christian Encarnacion-Strand"], "leg1_player": ["Christian Encarnacion Strand"]})
        for result in [display_frame(original), table_data_and_config(original)[0], format_display_frame(original)]:
            self.assertEqual(result.iloc[0].player, "C. Encarnacion-Strand")
            self.assertEqual(result.iloc[0].leg1_player, "C. Encarnacion-Strand")
        self.assertEqual(original.iloc[0].player, "Christian Encarnacion-Strand")
        self.assertEqual(merge_visible_editor_changes(original, format_display_frame(original)).iloc[0].player, original.iloc[0].player)

    def test_posting_and_export(self):
        original = pd.DataFrame({"player": ["Christian Encarnacion-Strand"], "signal": ["Test"], "odds": [450], "signal_stats": ["Test"]})
        posting = posting_frame(original, "Straight Bets")
        self.assertEqual(posting.iloc[0].player, "C. Encarnacion-Strand")
        self.assertNotIn("Christian Encarnacion", table_html(posting))
        self.assertEqual(clean_export_text(original.iloc[0].player), "C. Encarnacion-Strand")
