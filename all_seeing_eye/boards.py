from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# max_rank anchors rank-strength/movement scoring; it does not limit CSV rows.
BOARD_SPECS = {
    "gbm_top80": {
        "filename": "gbm_top80.csv",
        "label": "GBM Top 80",
        "layer": "gbm",
        "max_rank": 80,
        "weight": 0.22,
        "optional_scores": ("gbm_probability", "probability", "score"),
    },
    "gbm_progression_top80": {
        "filename": "gbm_progression_top80.csv",
        "label": "GBM Progression Top 80",
        "layer": "gbm",
        "max_rank": 80,
        "weight": 0.18,
        "optional_scores": ("progression_score", "gbm_probability", "probability", "score"),
    },
    "sequence_top150": {
        "filename": "sequence_top150.csv",
        "label": "Sequence Top 150",
        "layer": "sequence",
        "max_rank": 150,
        "weight": 0.24,
        "optional_scores": ("motif_score", "motif_confidence", "sequence_score", "hr_probability", "score"),
    },
    "pitcher_batter_top80": {
        "filename": "pitcher_batter_top80.csv",
        "label": "Pitcher/Batter Top 80",
        "layer": "pitch",
        "max_rank": 80,
        "weight": 0.24,
        "optional_scores": (
            "matchup_score",
            "pitch_shape_score",
            "batter_fit",
            "pitcher_weakness",
            "hr_edge_score",
            "score",
        ),
    },
}


@dataclass(frozen=True)
class BoardEntry:
    board_id: str
    player: str
    rank: int
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerSignal:
    player: str
    entries: dict[str, BoardEntry] = field(default_factory=dict)
    previous_entries: dict[str, BoardEntry] = field(default_factory=dict)
    historical_entries: dict[str, list[BoardEntry]] = field(default_factory=dict)
    has_previous_context: bool = False
    has_history_context: bool = False
