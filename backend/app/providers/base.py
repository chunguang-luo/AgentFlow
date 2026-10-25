from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class AgentResult:
    text: str
    data: dict[str, Any] = field(default_factory=dict)


class AgentProvider(Protocol):
    name: str

    async def execute(self, request: AgentRequest) -> AgentResult:
        """Execute an Agent request."""


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
