import asyncio

from app.providers.base import (
    AgentRequest,
    AgentResult,
    ProviderError,
    ProviderRegistry,
)


class MockProvider:
    name = "mock"

    async def execute(self, request: AgentRequest) -> AgentResult:
        settings = request.config.get("mock", {})
        if not isinstance(settings, dict):
            raise ProviderError("Mock provider config must be an object")

        delay = float(settings.get("delaySeconds", 0))
        if delay < 0:
            raise ProviderError("Mock provider delaySeconds must not be negative")

        fail_until_attempt = int(settings.get("failUntilAttempt", 0))
        if request.attempt <= fail_until_attempt:
            raise ProviderError(f"Mock provider failure at attempt {request.attempt}")

        await asyncio.sleep(delay)
        text = str(settings.get("output", f"Mock output for {request.execution_id}"))
        data = settings.get("data", {})
        if not isinstance(data, dict):
            raise ProviderError("Mock provider data must be an object")

        return AgentResult(text=text, data=data)


def build_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(MockProvider())
    return registry
