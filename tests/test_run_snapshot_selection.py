import json
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest


def snapshot_app(hub, day):
    from pathlib import Path
    from unittest.mock import patch
    import streamlit as st
    from all_seeing_eye.daily_hub import app

    if st.button("Use latest snapshot"):
        st.session_state["hub_select_latest"] = True
    if st.checkbox("Show snapshots", value=True):
        with patch.object(app, "HUB", Path(hub)):
            app.progress()
            selected = app.choose_run(day)
        st.session_state["selected_output"] = str(selected)


class RunSnapshotSelectionTests(unittest.TestCase):
    day = "2026-09-11"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name)
        self.morning = self.add_run("morning", "09:00")
        self.midday = self.add_run("midday", "12:00")
        self.app = AppTest.from_function(snapshot_app, args=(str(self.hub), self.day)).run()

    def add_run(self, run_id, finished):
        folder = self.hub / "runs" / self.day / run_id
        output = folder / self.day
        output.mkdir(parents=True, exist_ok=True)
        (folder / "status.json").write_text(json.dumps(dict(
            date=self.day, run_id=run_id, status="complete", mode="refresh", output=str(output),
            finished=f"{self.day}T{finished}:00+00:00", ready_players=5, pending_players=2)))
        return output

    def assert_selected(self, output):
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["selected_output"], str(output))

    def test_new_run_does_not_replace_selected_snapshot_on_rerun(self):
        self.assert_selected(self.midday)
        self.add_run("afternoon", "15:00")
        self.app.run()
        self.assert_selected(self.midday)

    def test_explicit_older_selection_survives_dropdown_reordering(self):
        self.app.selectbox[0].select("morning").run()
        self.assert_selected(self.morning)
        self.add_run("afternoon", "15:00")
        self.app.run()
        self.assert_selected(self.morning)

    def test_selection_survives_widget_cleanup(self):
        self.app.selectbox[0].select("morning").run()
        self.app.checkbox[0].uncheck().run()
        self.app.checkbox[0].check().run()
        self.assert_selected(self.morning)

    def test_explicit_latest_request_still_selects_new_run(self):
        afternoon = self.add_run("afternoon", "15:00")
        self.app.button[0].click().run()
        self.assert_selected(afternoon)

    def test_requested_refresh_selects_its_completed_snapshot(self):
        afternoon = self.add_run("afternoon", "15:00")
        self.app.session_state["hub_requested_run"] = "afternoon"
        (self.hub / "status.json").write_text((afternoon.parent / "status.json").read_text())
        self.app.run()
        self.assert_selected(afternoon)

    def test_unrequested_completed_run_does_not_switch_snapshot(self):
        afternoon = self.add_run("afternoon", "15:00")
        (self.hub / "status.json").write_text((afternoon.parent / "status.json").read_text())
        self.app.run()
        self.assert_selected(self.midday)

    def test_missing_snapshot_falls_back_to_latest_complete_run(self):
        self.app.selectbox[0].select("morning").run()
        status_path = self.morning.parent / "status.json"
        status = json.loads(status_path.read_text())
        status["status"] = "failed"
        status_path.write_text(json.dumps(status))
        self.app.run()
        self.assert_selected(self.midday)
