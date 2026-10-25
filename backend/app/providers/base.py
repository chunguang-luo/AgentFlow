from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """Raised when an Agent provider cannot complete a request."""


@dataclass(frozen=True, slots=True)
class AgentRequest:
    execution_id: str
    provider: str
    prompt: str
    attempt: int
    timeout_seconds: float
    config: dict[str, Any] = field(default_factory=dict)
    working_dir: Path | None = None
    artifact_dir: Path | None = None


@dataclass(frozen=True, slots=True)
class AgentLog:
    stream: str
    content: str


@dataclass(frozen=True, slots=True)
class AgentArtifact:
    relative_path: str
    storage_path: Path
    content_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class AgentResult:
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    logs: list[AgentLog] = field(default_factory=list)
    artifacts: list[AgentArtifact] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    available: bool
    version: str | None = None
    message: str | None = None


class AgentProvider(Protocol):
    name: str

    async def execute(self, request: AgentRequest) -> AgentResult:
        """Execute an Agent request."""

    async def check_health(self) -> ProviderHealth:
        """Check whether the provider executable is available."""


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AgentProvider] = {}

    def register(self, provider: AgentProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider is already registered: {provider.name}")
        self._providers[provider.name] = provider

    def get(self, name: str) -> AgentProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderError(f"Unknown provider: {name}") from exc

    def providers(self) -> list[AgentProvider]:
        return list(self._providers.values())


class ProviderExecutionError(ProviderError):
    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        timed_out: bool = False,
        logs: list[AgentLog] | None = None,
        artifacts: list[AgentArtifact] | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.logs = logs or []
        self.artifacts = artifacts or []
