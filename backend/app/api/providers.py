from fastapi import APIRouter
from pydantic import BaseModel

from app.providers.base import ProviderError
from app.providers.registry import build_default_provider_registry

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderResponse(BaseModel):
    name: str
    available: bool | None = None
    version: str | None = None
    message: str | None = None


@router.get("", response_model=list[ProviderResponse])
def list_providers() -> list[ProviderResponse]:
    return [
        ProviderResponse(name=provider.name)
        for provider in build_default_provider_registry().providers()
    ]


@router.post("/{provider_name}/health-check", response_model=ProviderResponse)
async def check_provider_health(provider_name: str) -> ProviderResponse:
    try:
        provider = build_default_provider_registry().get(provider_name)
    except ProviderError as exc:
        return ProviderResponse(name=provider_name, available=False, message=str(exc))

    health = await provider.check_health()
    return ProviderResponse(
        name=health.provider,
        available=health.available,
        version=health.version,
        message=health.message,
    )
