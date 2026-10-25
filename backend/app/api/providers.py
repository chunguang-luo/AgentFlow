from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth.dependencies import AuthContext, require_permission
from app.core.audit import record_audit
from app.db.session import SessionLocal, get_engine
from app.providers.base import ProviderError
from app.providers.registry import build_default_provider_registry

router = APIRouter(
    prefix="/api/providers",
    tags=["providers"],
    dependencies=[Depends(require_permission("providers:read"))],
)


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
async def check_provider_health(
    provider_name: str,
    request: Request,
    auth: AuthContext = Depends(require_permission("providers:check")),
) -> ProviderResponse:
    try:
        provider = build_default_provider_registry().get(provider_name)
    except ProviderError as exc:
        return ProviderResponse(name=provider_name, available=False, message=str(exc))

    health = await provider.check_health()
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        record_audit(
            session,
            action="provider.health_checked",
            target_type="provider",
            target_id=provider_name,
            user_id=auth.user.id,
            details={"available": health.available},
            request=request,
        )
        session.commit()
    return ProviderResponse(
        name=health.provider,
        available=health.available,
        version=health.version,
        message=health.message,
    )
