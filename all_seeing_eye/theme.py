"""Shared presentation for the Daily Baseball and Model 4 dashboards."""
from pathlib import Path

import streamlit as st

PEACH = "#ffc3a0"
BROWN = "#86664b"
OLIVE = "#848463"
CORAL = "#fb968a"
TEAL = "#a0c5c4"
CHART_COLORS = [OLIVE, CORAL, TEAL]


def apply_theme(*, enabled=True):
    _isolate_sequence_theme()
    st.html(Path(__file__).with_name("theme.css") if enabled else "<style></style>")


def _isolate_sequence_theme():
    # Streamlit 1.56 has no per-page theme API. Override only this browser
    # session's theme message so Sequence keeps its original native widgets.
    from streamlit.runtime import exists, get_instance
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    context = get_script_run_ctx()
    if context is None or not exists():
        return
    info = get_instance()._session_mgr.get_active_session_info(context.session_id)
    if info is None or getattr(info.session, "_model4_theme_installed", False):
        return
    session = info.session
    original = session._create_new_session_message

    def create_message(*args, **kwargs):
        message = original(*args, **kwargs)
        try:
            sequence = session.session_state["hub_page"] == "Sequence Lab"
        except KeyError:
            sequence = False
        if sequence:
            theme = message.new_session.custom_theme
            theme.Clear()
            theme.base = theme.DARK
            theme.primary_color = "#c4c6ca"
        return message

    session._create_new_session_message = create_message
    session._model4_theme_installed = True


def style_chart(chart, *, axis_label_size=11):
    return (chart.configure(background=PEACH, font="sans-serif")
            .configure_axis(labelColor=BROWN, titleColor=BROWN, domain=False,
                            labelFontSize=axis_label_size, titleFontSize=12,
                            tickColor="#dcae90", gridColor="#86664b", gridOpacity=.12,
                            gridDash=[2, 5], labelPadding=8, titlePadding=12)
            .configure_legend(labelColor=BROWN, titleColor=BROWN, orient="bottom",
                              title=None, columns=1)
            .configure_view(stroke=None)
            .configure_line(strokeWidth=3, strokeCap="round", strokeJoin="round")
            .configure_range(category=CHART_COLORS))
