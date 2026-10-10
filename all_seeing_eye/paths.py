"""Shared locations for optional upstream projects and their Python runtime."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def configured_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else default


def project_path(name: str, sibling: str, legacy: Path) -> Path:
    default = ROOT.parent / sibling
    if not default.is_dir() and legacy.is_dir():
        default = legacy
    return configured_path(name, default)


GBM = project_path("MODEL4_GBM_DIR", "Homerun_Predictor", Path.home() / "Desktop/Homerun_Predictor")
SEQUENCE = project_path(
    "MODEL4_SEQUENCE_DIR", "sequence_home_run_lab",
    Path.home() / "Local Projects/Goal practice/fresh_folder/sequence_home_run_lab",
)
MATCHUP = project_path("MODEL4_MATCHUP_DIR", "Model_3", Path.home() / "Local Projects/Model_3")
UPSTREAM_PYTHON = configured_path("MODEL4_UPSTREAM_PYTHON", Path(sys.executable))
