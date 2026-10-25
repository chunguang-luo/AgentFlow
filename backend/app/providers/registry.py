from app.providers.base import ProviderRegistry
from app.providers.cli import build_claude_provider, build_codex_provider
from app.providers.mock import MockProvider


def build_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(MockProvider())
    registry.register(build_claude_provider())
    registry.register(build_codex_provider())
    return registry
