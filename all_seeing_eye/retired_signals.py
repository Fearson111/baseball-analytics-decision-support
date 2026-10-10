from __future__ import annotations

import pandas as pd

# Retired rules remain identifiable in saved snapshots and frozen audit records.
RETIRED_SIGNALS = frozenset({
    "Model Rank 1-5 / Edge -10% to -5%",
    "5-step + contact quality + Model 2 rank 1-10 + GBM top25",
    "High-lift 5 + GBM rank 1-10 + edge -10% to 0%",
    "High-lift 5 + GBM rank 1-25 + edge -10% to -5%",
})


def without_retired_signals(frame: pd.DataFrame) -> pd.DataFrame:
    if "signal" not in frame:
        return frame.copy()
    return frame.loc[~frame["signal"].isin(RETIRED_SIGNALS)].copy()
