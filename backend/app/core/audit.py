from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()[:64]
    return request.client.host if request.client else None


def record_audit(
    session: Session,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id[:64] if target_id else None,
        details=details or {},
        ip_address=client_ip(request) if request else None,
        user_agent=request.headers.get("User-Agent")[:512] if request else None,
    )
    session.add(entry)
    session.flush()
    return entry
