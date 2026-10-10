from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path

VERSION = "financial-v1"


@dataclass
class Config:
    price_breaks: list = field(default_factory=lambda: [300, 400, 500, 600, 800])
    prior_strength: float = 30
    effective_sample_cap: float = 100
    min_sample: int = 25
    credible_mass: float = .90
    min_p_positive_ev: float = .90
    min_edge_pp: float = 1.5
    max_interval_width: float = .20
    max_quote_age_minutes: float = 60
    kelly_fraction: float = .25
    starting_bankroll: float = 100
    max_stake: float = 1
    max_daily: float = 5
    max_game: float = 2
    max_team: float = 2
    max_family: float = 3
    max_model: float = 3
    ridge: float = 10
    min_train: int = 150
    min_oos: int = 60
    use_meta: bool = False
    require_confirmed: bool = True

    def validate(self):
        for name, value in asdict(self).items():
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{name} must be a positive finite number.")
        for name in ("credible_mass", "min_p_positive_ev", "max_interval_width", "kelly_fraction"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"{name} must be between zero and one.")
        if not self.price_breaks or any(not math.isfinite(v) or v < 100 for v in self.price_breaks):
            raise ValueError("Price bucket boundaries must be positive American odds of at least +100.")
        if sorted(set(self.price_breaks)) != self.price_breaks:
            raise ValueError("Price bucket boundaries must be unique and increasing.")
        return self

    @property
    def signature(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]


def load(root: Path):
    path = root / "DAILY_BASEBALL" / "financial" / "config.json"
    if not path.exists():
        return Config()
    return Config(**json.loads(path.read_text())).validate()


def save(root: Path, config: Config):
    from ..daily_hub.runner import atomic_json
    config.validate()
    atomic_json(root / "DAILY_BASEBALL" / "financial" / "config.json", asdict(config))

