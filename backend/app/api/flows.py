from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, require_permission
from app.core.audit import record_audit
from app.core.errors import APIError
from app.db.models import Flow, FlowVersion
from app.db.session import SessionLocal, get_engine
from app.flows.schema import parse_flow_definition
from app.flows.service import FlowNotFoundError, FlowService

router = APIRouter(prefix="/api/flows", tags=["flows"])


class FlowSummary(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    current_version: int | None
    owner_id: str
    created_at: datetime
    updated_at: datetime


class FlowDetail(FlowSummary):
    draft_definition: dict[str, Any] | None


class FlowVersionResponse(BaseModel):
    id: str
    flow_id: str
    version: int
    definition: dict[str, Any]
    schema_version: str
    created_by: str
    created_at: datetime


class FlowPage(BaseModel):
    items: list[FlowSummary]
    total: int
    page: int
    page_size: int


class ValidateFlowResponse(BaseModel):
    valid: bool
    definition: dict[str, Any]


def _flow_session() -> Session:
    SessionLocal.configure(bind=get_engine())
    return SessionLocal()


def _summary(flow: Flow) -> FlowSummary:
    return FlowSummary(
        id=flow.id,
        name=flow.name,
        description=flow.description,
        status=flow.status,
        current_version=flow.current_version,
        owner_id=flow.owner_id,
        created_at=flow.created_at,
        updated_at=flow.updated_at,
    )


def _version(version: FlowVersion) -> FlowVersionResponse:
    return FlowVersionResponse(
        id=version.id,
        flow_id=version.flow_id,
        version=version.version,
        definition=version.definition,
        schema_version=version.schema_version,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _parse_definition(data: dict[str, Any]) -> Any:
    try:
        return parse_flow_definition(data)
    except Exception as exc:
        raise APIError(
            status_code=422,
            code="flow_validation_error",
            message="Flow definition validation failed.",
            details={"errors": [str(exc)]},
        ) from exc


@router.get("", response_model=FlowPage)
def list_flows(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str | None = None,
    status: str | None = None,
    owner_id: str | None = None,
    sort: Literal["created_at_desc", "created_at_asc", "name_asc", "updated_at_desc"] = (
        "created_at_desc"
    ),
    _auth: AuthContext = Depends(require_permission("flows:read")),
) -> FlowPage:
    with _flow_session() as session:
        statement = select(Flow)
        count_statement = select(func.count()).select_from(Flow)
        if name:
            statement = statement.where(Flow.name.ilike(f"%{name}%"))
            count_statement = count_statement.where(Flow.name.ilike(f"%{name}%"))
        if status:
            statement = statement.where(Flow.status == status)
            count_statement = count_statement.where(Flow.status == status)
        if owner_id:
            statement = statement.where(Flow.owner_id == owner_id)
            count_statement = count_statement.where(Flow.owner_id == owner_id)

        order_by = {
            "created_at_desc": Flow.created_at.desc(),
            "created_at_asc": Flow.created_at.asc(),
            "name_asc": Flow.name.asc(),
            "updated_at_desc": Flow.updated_at.desc(),
        }[sort]
        rows = session.scalars(
            statement.order_by(order_by).offset((page - 1) * page_size).limit(page_size)
        ).all()
        total = session.scalar(count_statement) or 0
        return FlowPage(
            items=[_summary(flow) for flow in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.post("", response_model=FlowDetail, status_code=201)
def create_flow(
    definition: dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_permission("flows:write")),
) -> FlowDetail:
    parsed = _parse_definition(definition)
    with _flow_session() as session:
        flow = FlowService(session).create(parsed, owner_id=auth.user.id)
        record_audit(
            session,
            action="flow.created",
            target_type="flow",
            target_id=flow.id,
            user_id=auth.user.id,
            request=request,
        )
        session.commit()
        return FlowDetail(**_summary(flow).model_dump(), draft_definition=flow.draft_definition)


@router.post("/validate", response_model=ValidateFlowResponse)
def validate_flow(
    definition: dict[str, Any],
    _auth: AuthContext = Depends(require_permission("flows:write")),
) -> ValidateFlowResponse:
    parsed = _parse_definition(definition)
    return ValidateFlowResponse(valid=True, definition=parsed.model_dump(mode="json"))


@router.post("/import", response_model=FlowDetail, status_code=201)
def import_flow(
    definition: dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_permission("flows:write")),
) -> FlowDetail:
    parsed = _parse_definition(definition)
    with _flow_session() as session:
        flow = FlowService(session).create(parsed, owner_id=auth.user.id)
        record_audit(
            session,
            action="flow.imported",
            target_type="flow",
            target_id=flow.id,
            user_id=auth.user.id,
            request=request,
        )
        session.commit()
        return FlowDetail(**_summary(flow).model_dump(), draft_definition=flow.draft_definition)


@router.get("/{flow_id}", response_model=FlowDetail)
def get_flow(
    flow_id: str,
    _auth: AuthContext = Depends(require_permission("flows:read")),
) -> FlowDetail:
    with _flow_session() as session:
        flow = FlowService(session).get(flow_id)
        return FlowDetail(**_summary(flow).model_dump(), draft_definition=flow.draft_definition)


@router.put("/{flow_id}", response_model=FlowDetail)
def update_flow(
    flow_id: str,
    definition: dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_permission("flows:write")),
) -> FlowDetail:
    parsed = _parse_definition(definition)
    with _flow_session() as session:
        service = FlowService(session)
        flow = service.update_draft(flow_id, parsed)
        record_audit(
            session,
            action="flow.updated",
            target_type="flow",
            target_id=flow.id,
            user_id=auth.user.id,
            request=request,
        )
        session.commit()
        return FlowDetail(**_summary(flow).model_dump(), draft_definition=flow.draft_definition)


@router.post("/{flow_id}/publish", response_model=FlowVersionResponse, status_code=201)
def publish_flow(
    flow_id: str,
    request: Request,
    auth: AuthContext = Depends(require_permission("flows:publish")),
) -> FlowVersionResponse:
    with _flow_session() as session:
        version = FlowService(session).publish(flow_id, published_by=auth.user.id)
        record_audit(
            session,
            action="flow.published",
            target_type="flow",
            target_id=flow_id,
            user_id=auth.user.id,
            details={"version": version.version},
            request=request,
        )
        session.commit()
        return _version(version)


@router.get("/{flow_id}/versions", response_model=list[FlowVersionResponse])
def list_flow_versions(
    flow_id: str,
    _auth: AuthContext = Depends(require_permission("flows:read")),
) -> list[FlowVersionResponse]:
    with _flow_session() as session:
        FlowService(session).get(flow_id)
        versions = session.scalars(
            select(FlowVersion)
            .where(FlowVersion.flow_id == flow_id)
            .order_by(FlowVersion.version.desc())
        ).all()
        return [_version(version) for version in versions]


@router.get("/{flow_id}/versions/{version}", response_model=FlowVersionResponse)
def get_flow_version(
    flow_id: str,
    version: int,
    _auth: AuthContext = Depends(require_permission("flows:read")),
) -> FlowVersionResponse:
    with _flow_session() as session:
        result = session.scalar(
            select(FlowVersion).where(
                FlowVersion.flow_id == flow_id,
                FlowVersion.version == version,
            )
        )
        if result is None:
            raise FlowNotFoundError(f"Flow {flow_id} version {version} was not found")
        return _version(result)


@router.get("/{flow_id}/export")
def export_flow(
    flow_id: str,
    request: Request,
    version: int | None = None,
    draft: bool = False,
    auth: AuthContext = Depends(require_permission("flows:read")),
) -> dict[str, Any]:
    with _flow_session() as session:
        definition = FlowService(session).export(
            flow_id,
            version=version,
            draft=draft,
        )
        record_audit(
            session,
            action="flow.exported",
            target_type="flow",
            target_id=flow_id,
            user_id=auth.user.id,
            details={"version": version, "draft": draft},
            request=request,
        )
        session.commit()
        return definition
