from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest


def correction_app(root, day):
    from pathlib import Path
    from unittest.mock import patch
    import streamlit as st
    from all_seeing_eye.daily_hub import app

    root = Path(root)
    out = root / "run" / day
    def capture(out, correction, **kwargs):
        st.session_state["submitted"] = {**correction, **kwargs}
    with patch.object(app, "HUB", root), patch.object(app, "rebuild_correction", capture):
        app.player_corrections(out, app.load_csv(out.parent / "market_board.csv"), prefix="gbm", missing_only=True)


class GBMCorrectionsUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.day = date.today().isoformat()
        (self.root / "run" / self.day).mkdir(parents=True)
        (self.root / "run" / "status.json").write_text(json.dumps({"mode": "full"}))
        self.rows = [dict(player_name=name, player_id=pid, game_id=gid, team_abbrev="SEA",
                          book_american_odds=odds, bookmaker_used=book, lineup_status=status)
                     for name, pid, gid, odds, book, status in [
                         ("Alpha Missing", "1", "10", "", "", "not_confirmed"),
                         ("Beta Missing", "2", "10", "", "", "not_confirmed"),
                         ("Gamma Priced", "3", "10", "500", "DraftKings", "confirmed"),
                         ("Out Player", "4", "10", "", "", "out"),
                         ("Alpha Missing", "1", "20", "", "", "not_confirmed")]]
        pd.DataFrame(self.rows).to_csv(self.root / "run" / "market_board.csv", index=False)
        self.app = AppTest.from_function(correction_app, args=(str(self.root), self.day)).run()

    def test_missing_filter_and_player_game_identity(self):
        self.assertFalse(self.app.exception)
        options = self.app.selectbox[0].options
        self.assertEqual(len(options), 3)
        self.assertTrue(any("Game 20" in option for option in options))
        self.assertFalse(any("Priced" in option or "Out Player" in option for option in options))
        self.app.toggle[0].set_value(False).run()
        self.assertEqual(len(self.app.selectbox[0].options), 5)

    def test_enter_odds_submits_correction_not_wager(self):
        self.app.text_input[0].input("+550")
        self.app.selectbox[1].select("Fanatics")
        self.app.button[0].click().run()
        self.assertFalse(self.app.exception)
        submitted = self.app.session_state["submitted"]
        self.assertEqual(submitted["odds"], 550)
        self.assertEqual(submitted["sportsbook"], "Fanatics")
        self.assertEqual((submitted["game_id"], submitted["player_id"]), ("10", "1"))
        self.assertFalse(submitted["out"])

    def test_mark_out_requires_no_odds(self):
        self.app.checkbox[0].check()
        self.app.button[0].click().run()
        submitted = self.app.session_state["submitted"]
        self.assertTrue(submitted["out"])
        self.assertIsNone(submitted["odds"])

    def test_invalid_odds_do_not_submit(self):
        for value in ("", "hello", "nan", "inf", "+50", "450.5"):
            with self.subTest(value=value):
                self.app.text_input[0].input(value)
                self.app.button[0].click().run()
                self.assertEqual(len(self.app.error), 1)
                self.assertNotIn("submitted", self.app.session_state)

    def test_drafts_do_not_carry_over_to_another_player_or_game(self):
        self.app.text_input[0].input("+800")
        self.app.checkbox[0].check()
        self.app.selectbox[0].select(("20", "1")).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.text_input[0].value, "")
        self.assertFalse(self.app.checkbox[0].value)

    def test_clear_existing_out_correction(self):
        (self.root / "overrides").mkdir()
        (self.root / "overrides" / f"{self.day}.json").write_text(json.dumps([
            dict(game_id="10", player_id="4", out=True)]))
        self.app.toggle[0].set_value(False).run()
        self.app.selectbox[0].select(("10", "4")).run()
        self.assertTrue(self.app.checkbox[0].value)
        self.assertFalse(self.app.button[1].disabled)
        self.app.button[1].click().run()
        self.assertEqual(self.app.session_state["submitted"], dict(game_id="10", player_id="4", clear=True))

    def test_saved_preview_has_no_edit_controls(self):
        (self.root / "run" / "status.json").write_text(json.dumps({"mode": "saved"}))
        self.app.run()
        self.assertFalse(self.app.button)
        self.assertFalse(self.app.selectbox)


if __name__ == "__main__":
    unittest.main()
