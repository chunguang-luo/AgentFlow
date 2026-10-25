from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.models import CurrentUser
from app.auth.service import AuthenticationError, AuthService
from app.core.config import get_settings
from app.core.errors import APIError
from app.core.rbac import has_permission
from app.db.session import get_session

SESSION_COOKIE = "agentflow_session"


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: CurrentUser
    token: str
    token_source: str


def _extract_token(request: Request) -> tuple[str, str] | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:].strip(), "header"
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        return token, "cookie"
    return None


def _validate_origin(request: Request, token_source: str) -> None:
    if token_source != "cookie" or request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("Origin")
    if not origin:
        raise APIError(
            status_code=403,
            code="csrf_origin_required",
            message="An allowed Origin header is required for cookie-authenticated writes.",
        )

    settings = get_settings()
    request_origin = str(request.base_url).rstrip("/")
    allowed = set(settings.cors_origins) | {request_origin}
    if origin not in allowed:
        raise APIError(
            status_code=403,
            code="csrf_origin_rejected",
            message="Request Origin is not allowed.",
        )


def get_auth_context(
    request: Request,
    session: Session = Depends(get_session),
) -> AuthContext:
    extracted = _extract_token(request)
    if extracted is None:
        raise APIError(
            status_code=401,
            code="authentication_required",
            message="Authentication is required.",
        )
    token, source = extracted
    try:
        user, _user_session = AuthService(session).resolve_session(token)
    except AuthenticationError as exc:
        raise APIError(
            status_code=401,
            code="authentication_required",
            message="Authentication is required.",
        ) from exc

    _validate_origin(request, source)
    return AuthContext(
        user=CurrentUser(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        ),
        token=token,
        token_source=source,
    )


def require_permission(permission: str):
    def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not has_permission(auth.user.role, permission):
            raise APIError(
                status_code=403,
                code="permission_denied",
                message=f"Permission is required: {permission}",
            )
        return auth

    return dependency
