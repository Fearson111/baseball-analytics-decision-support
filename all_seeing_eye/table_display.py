from __future__ import annotations

from copy import deepcopy
import math
import re

import pandas as pd


def display_name(value: str) -> str:
    return re.sub(r"\bChristian\s+Encarnaci[oó]n[\s\-–—]+Strand\b",
                  "C. Encarnacion-Strand", value, flags=re.IGNORECASE)


def decimal_places(column: str) -> int:
    name = str(column).lower()
    return 2 if any(word in name for word in ("roi", "profit", "units", "stake", "p/l", "drawdown")) else 1


def display_value(value: object, column: str = "") -> str:
    if value is None or value is pd.NA:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>", "nat"}:
        return ""
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([%xu]?)", text)
    if not match:
        return display_name(text)
    number = float(match[1])
    if not math.isfinite(number):
        return ""
    places = 2 if match[2] == "u" else decimal_places(column)
    sign = "+" if text.startswith("+") else ""
    if number.is_integer() and not match[2] and places == 1:
        return sign + str(int(number))
    return f"{number:{sign}.{places}f}{match[2]}"


def display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output:
        output[column] = output[column].map(lambda value: display_value(value, column)).astype(object)
    return output


def table_data_and_config(frame: pd.DataFrame, column_config=None):
    # Numeric columns keep their real values for sorting; only their rendering changes.
    output = frame.copy()
    config = deepcopy(column_config or {})
    for column in output:
        if pd.api.types.is_float_dtype(output[column].dtype):
            existing = config.get(column, {})
            if existing is None:
                continue
            if isinstance(existing, str):
                existing = {"label": existing}
            settings = dict(existing)
            type_config = dict(settings.get("type_config") or {})
            type_config.update(type="number", format=f"%.{decimal_places(column)}f")
            settings["type_config"] = type_config
            config[column] = settings
        elif pd.api.types.is_object_dtype(output[column].dtype) or pd.api.types.is_string_dtype(output[column].dtype):
            output[column] = output[column].map(lambda value: display_value(value, column))
    return output, config


def dataframe(data=None, *args, **kwargs):
    import streamlit as st
    if isinstance(data, pd.DataFrame):
        data, kwargs["column_config"] = table_data_and_config(data, kwargs.get("column_config"))
    return st.dataframe(data, *args, **kwargs)

def sequence_table_data_and_config(frame: pd.DataFrame, column_config=None):
    output, config = table_data_and_config(frame, column_config)
    # Sequence stores probabilities as fractions; scale only the display copy.
    for column in ("hr_probability", "avg_projected_probability", "top_projected_probability", "actual_hr_rate"):
        if column not in frame or config.get(column, {}) is None:
            continue
        output[column] = pd.to_numeric(frame[column], errors="coerce") * 100
        existing = config.get(column, {})
        settings = {"label": existing} if isinstance(existing, str) else dict(existing)
        settings["type_config"] = {**(settings.get("type_config") or {}), "type": "number", "format": "%.1f%%"}
        config[column] = settings
    return output, config


def sequence_dataframe(data=None, *args, **kwargs):
    import streamlit as st
    if isinstance(data, pd.DataFrame):
        data, kwargs["column_config"] = sequence_table_data_and_config(data, kwargs.get("column_config"))
    return st.dataframe(data, *args, **kwargs)


