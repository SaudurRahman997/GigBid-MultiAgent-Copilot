"""GigSim runtime settings, read from environment variables (prefix GIGSIM_)."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PKG = Path(__file__).resolve().parent
REPO = PKG.parent

DEFAULT_TOKENS = (
    "ai_ml:dev-token-ai-ml,fullstack:dev-token-fullstack,"
    "data_analyst:dev-token-data-analyst,reviewer:dev-token-reviewer"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GIGSIM_", extra="ignore")

    database_url: str = "sqlite:///./gigsim.db"
    seed: int = 42
    error_rate: float = 0.03  # share of requests answered with a simulated 5xx
    lost_response_share: float = 0.33  # of 5xx on submit: processed first, then error returned
    rate_limit_per_min: int = 60
    release_interval_min: float = 10.0  # real minutes between release-loop runs
    time_scale: float = (
        60.0  # simulated seconds per real second (0 = clock only moves on /admin/tick)
    )
    policy_version: str = "v1"
    data_dir: Path = REPO / "data"
    tokens: str = DEFAULT_TOKENS  # "user:token,user:token"
    admin_token: str = "dev-admin-token"
    include_heldout: bool = True  # load data/heldout if present (never committed)

    @cached_property
    def token_map(self) -> dict[str, str]:
        pairs = (p.split(":", 1) for p in self.tokens.split(",") if ":" in p)
        return {token.strip(): user.strip() for user, token in pairs}

    @cached_property
    def policy(self) -> dict:
        path = PKG / "policy" / f"{self.policy_version}.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    @cached_property
    def model(self) -> dict:
        return yaml.safe_load((PKG / "config.yaml").read_text(encoding="utf-8"))
