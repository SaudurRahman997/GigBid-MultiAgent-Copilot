"""Settings shared by the three GigBid MCP servers (env prefix MCP_)."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO = Path(__file__).resolve().parents[2]
DEFAULT_TOKENS = (
    "ai_ml:dev-mcp-ai-ml,fullstack:dev-mcp-fullstack,"
    "data_analyst:dev-mcp-data-analyst,reviewer:dev-mcp-reviewer"
)


def parse_pairs(value: str) -> dict[str, str]:
    """'user:token,user:token' -> {token: user}."""
    pairs = (p.split(":", 1) for p in value.split(",") if ":" in p)
    return {token.strip(): user.strip() for user, token in pairs}


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_", extra="ignore")

    tokens: str = DEFAULT_TOKENS  # bearer tokens accepted by every server ("user:token,...")
    user_personas: str = "reviewer:ai_ml"  # users whose persona differs from their user id
    dev_user: str | None = None  # in-memory/stdio only: user when there is no HTTP bearer token
    database_url: str = "sqlite:///./mcp.db"  # audit log, idempotency, workspace mocks
    data_dir: Path = REPO / "data"
    host: str = "127.0.0.1"
    allowed_hosts: str = "localhost:*,127.0.0.1:*"  # DNS-rebinding protection (comma list)
    rate_limit_per_min: int = 50  # per user, below GigSim's 60/min
    public_url: str = "http://localhost"  # used in OAuth protected-resource metadata
    # Marketplace -> GigSim
    gigsim_url: str = "http://localhost:8100"
    gigsim_tokens: str = (
        "ai_ml:dev-token-ai-ml,fullstack:dev-token-fullstack,"
        "data_analyst:dev-token-data-analyst,reviewer:dev-token-reviewer"
    )
    gigsim_timeout_s: float = 10.0
    gigsim_max_retries: int = 4

    @cached_property
    def token_map(self) -> dict[str, str]:
        return parse_pairs(self.tokens)

    def persona_for(self, user: str) -> str:
        overrides = {u: p for p, u in parse_pairs(self.user_personas).items()}
        return overrides.get(user, user)

    @cached_property
    def gigsim_token_for_user(self) -> dict[str, str]:
        return {user: token for token, user in parse_pairs(self.gigsim_tokens).items()}

    @cached_property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
