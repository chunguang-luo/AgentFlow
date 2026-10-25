import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.db.models import User, UserSession, utc_now

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    pass


class AuthService:
    def __init__(self, session: Session):
        self.session = session

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str = "viewer",
        email: str | None = None,
        display_name: str | None = None,
    ) -> User:
        if role not in {"admin", "editor", "operator", "viewer"}:
            raise ValueError(f"Invalid role: {role}")
        user = User(
            username=username,
            email=email,
            display_name=display_name or username,
            password_hash=hash_password(password),
            role=role,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def authenticate(self, username: str, password: str) -> User:
        user = self.session.scalar(select(User).where(User.username == username))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username or password")
        return user

    def issue_session(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[UserSession, str]:
        token = new_session_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().session_ttl_minutes)
        user_session = UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            ip_address=ip_address,
            user_agent=user_agent[:512] if user_agent else None,
            expires_at=expires_at,
        )
        self.session.add(user_session)
        self.session.flush()
        return user_session, token

    def resolve_session(self, token: str) -> tuple[User, UserSession]:
        user_session = self.session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        if user_session is None:
            raise AuthenticationError("Authentication required")
        expires_at = user_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise AuthenticationError("Authentication required")

        user = self.session.get(User, user_session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Authentication required")

        user_session.last_used_at = utc_now()
        self.session.flush()
        self.session.commit()
        return user, user_session

    def logout(self, token: str) -> None:
        user_session = self.session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        if user_session is not None:
            self.session.delete(user_session)
            self.session.flush()


def ensure_bootstrap_admin(session: Session) -> User | None:
    settings = get_settings()
    existing = session.scalar(
        select(User).where(User.username == settings.bootstrap_admin_username)
    )
    if existing is not None:
        return None

    password = settings.bootstrap_admin_password
    if not password and settings.environment in {"development", "test"}:
        password = "agentflow-admin"

    if not password:
        logger.warning("No bootstrap admin created because no password is configured")
        return None

    admin = AuthService(session).create_user(
        username=settings.bootstrap_admin_username,
        password=password,
        role="admin",
        display_name="Bootstrap Admin",
    )
    session.commit()
    logger.info("Created bootstrap admin user %s", admin.username)
    return admin
