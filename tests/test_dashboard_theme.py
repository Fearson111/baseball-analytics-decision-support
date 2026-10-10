"""The native theme boundary must remain local to each browser session."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

from all_seeing_eye.theme import _isolate_sequence_theme


class DashboardThemeTests(unittest.TestCase):
    def make_session(self):
        def original(*args, **kwargs):
            message = ForwardMsg()
            message.new_session.custom_theme.background_color = "#ffc3a0"
            message.new_session.custom_theme.primary_color = "#86664b"
            message.new_session.custom_theme.sidebar.background_color = "#ffc3a0"
            message.new_session.script_run_id = "unchanged-run"
            return message
        return SimpleNamespace(session_state={}, _create_new_session_message=original)

    def install(self, session):
        manager = SimpleNamespace(get_active_session_info=lambda _: SimpleNamespace(session=session))
        runtime = SimpleNamespace(_session_mgr=manager)
        with patch("streamlit.runtime.exists", return_value=True), \
             patch("streamlit.runtime.get_instance", return_value=runtime), \
             patch("streamlit.runtime.scriptrunner.get_script_run_ctx", return_value=SimpleNamespace(session_id="test")):
            _isolate_sequence_theme()

    def test_sequence_theme_restores_without_changing_other_sessions(self):
        sequence, normal = self.make_session(), self.make_session()
        self.install(sequence)
        self.install(normal)
        sequence.session_state["hub_page"] = "Sequence Lab"
        message = sequence._create_new_session_message()
        theme = message.new_session.custom_theme
        self.assertEqual(theme.base, theme.DARK)
        self.assertEqual(theme.primary_color, "#c4c6ca")
        self.assertFalse(theme.HasField("sidebar"))
        self.assertEqual(message.new_session.script_run_id, "unchanged-run")
        self.assertEqual(normal._create_new_session_message().new_session.custom_theme.background_color, "#ffc3a0")
        sequence.session_state["hub_page"] = "Daily Board"
        self.assertEqual(sequence._create_new_session_message().new_session.custom_theme.background_color, "#ffc3a0")

    def test_reruns_do_not_stack_the_theme_wrapper(self):
        session = self.make_session()
        self.install(session)
        wrapped = session._create_new_session_message
        self.install(session)
        self.assertIs(session._create_new_session_message, wrapped)
