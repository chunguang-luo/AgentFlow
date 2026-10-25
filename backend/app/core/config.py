from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings.

    Environment variables use the `AGENTFLOW_` prefix. List values are parsed
    as JSON, which keeps docker-compose and .env examples unambiguous.
    """

    app_name: str = "AgentFlow"
    environment: Literal["development", "test", "production"] = "development"
    db_path: Path = Path(".agentflow/agentflow.db")
    workspace_root: Path = Path(".agentflow/workspaces")
    artifact_root: Path = Path(".agentflow/artifacts")
    claude_cli_path: str = "claude"
    codex_cli_path: str = "codex"
    agent_env_allowlist: list[str] = [
        "HOME",
        "PATH",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "XDG_CONFIG_HOME",
    ]
    max_agent_output_bytes: int = Field(default=2_000_000, gt=0)
    max_agent_log_bytes: int = Field(default=1_000_000, gt=0)
    max_artifacts_per_step: int = Field(default=100, gt=0)
    max_artifact_bytes: int = Field(default=100_000_000, gt=0)
    cors_origins: list[str] = []
    log_level: str = "INFO"
    api_prefix: str = "/api"

    model_config = SettingsConfigDict(env_prefix="AGENTFLOW_", env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        absolute_db_path = self.db_path.expanduser().resolve()
        return f"sqlite:///{absolute_db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
