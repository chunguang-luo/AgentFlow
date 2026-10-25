from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import SESSION_COOKIE, AuthContext, get_auth_context
from app.auth.models import CurrentUser, LoginRequest, LoginResponse
from app.auth.service import AuthenticationError, AuthService
from app.core.audit import client_ip, record_audit
from app.core.config import get_settings
from app.core.errors import APIError
from app.db.session import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    request_data: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    service = AuthService(session)
    try:
        user = service.authenticate(request_data.username, request_data.password)
    except AuthenticationError:
        record_audit(
            session,
            action="auth.login_failed",
            target_type="user",
            target_id=request_data.username,
            details={"username": request_data.username},
            request=request,
        )
        session.commit()
        raise APIError(
            status_code=401,
            code="invalid_credentials",
            message="Invalid username or password.",
        ) from None

    _user_session, token = service.issue_session(
        user,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    record_audit(
        session,
        action="auth.login_succeeded",
        target_type="user",
        target_id=user.id,
        user_id=user.id,
        request=request,
    )
    session.commit()

    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
    )
    return LoginResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        token=token,
    )


@router.post("/logout", response_model=CurrentUser)
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
) -> CurrentUser:
    AuthService(session).logout(auth.token)
    record_audit(
        session,
        action="auth.logout",
        target_type="user",
        target_id=auth.user.id,
        user_id=auth.user.id,
        request=request,
    )
    session.commit()
    response.delete_cookie(SESSION_COOKIE, secure=get_settings().environment == "production")
    return auth.user


@router.get("/me", response_model=CurrentUser)
def me(auth: AuthContext = Depends(get_auth_context)) -> CurrentUser:
    return auth.user
