from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.dependencies import AuthContext, require_permission
from app.db.models import AuditLog
from app.db.session import SessionLocal, get_engine

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: str
    user_id: str | None
    action: str
    target_type: str
    target_id: str | None
    details: dict
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    user_id: str | None = None,
    target_type: str | None = None,
    sort: Literal["created_at_desc", "created_at_asc"] = "created_at_desc",
    _auth: AuthContext = Depends(require_permission("audit:read")),
) -> AuditLogPage:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        statement = select(AuditLog)
        count_statement = select(func.count()).select_from(AuditLog)
        if action:
            statement = statement.where(AuditLog.action == action)
            count_statement = count_statement.where(AuditLog.action == action)
        if user_id:
            statement = statement.where(AuditLog.user_id == user_id)
            count_statement = count_statement.where(AuditLog.user_id == user_id)
        if target_type:
            statement = statement.where(AuditLog.target_type == target_type)
            count_statement = count_statement.where(AuditLog.target_type == target_type)

        order_by = {
            "created_at_desc": AuditLog.created_at.desc(),
            "created_at_asc": AuditLog.created_at.asc(),
        }[sort]
        logs = session.scalars(
            statement.order_by(order_by).offset((page - 1) * page_size).limit(page_size)
        ).all()
        total = session.scalar(count_statement) or 0
        return AuditLogPage(
            items=[
                AuditLogResponse(
                    id=log.id,
                    user_id=log.user_id,
                    action=log.action,
                    target_type=log.target_type,
                    target_id=log.target_id,
                    details=log.details,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                    created_at=log.created_at,
                )
                for log in logs
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
