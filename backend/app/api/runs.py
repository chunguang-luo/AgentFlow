import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.auth.dependencies import AuthContext, require_permission
from app.core.audit import record_audit
from app.db.models import AgentLogRecord, Run, RunEvent, StepRun
from app.db.session import SessionLocal, get_engine
from app.engine.manager import run_task_manager
from app.engine.runs import RunNotFoundError, RunService

router = APIRouter(
    prefix="/api/runs",
    tags=["runs"],
    dependencies=[Depends(require_permission("runs:read"))],
)


class CreateRunRequest(BaseModel):
    flow_id: str = Field(min_length=1)
    flow_version: int | None = Field(default=None, ge=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=255)


class StepRunResponse(BaseModel):
    id: str
    step_id: str
    step_type: str
    status: str
    attempt: int
    error: str | None


class RunResponse(BaseModel):
    id: str
    flow_id: str
    flow_version: int
    status: str
    inputs: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None


class AgentLogResponse(BaseModel):
    id: str
    step_run_id: str
    stream: str
    sequence: int
    content: str


class RunPage(BaseModel):
    items: list[RunResponse]
    total: int
    page: int
    page_size: int


def serialize_run(run: Run) -> RunResponse:
    return RunResponse(
        id=run.id,
        flow_id=run.flow_id,
        flow_version=run.flow_version,
        status=run.status,
        inputs=run.inputs,
        result=run.result,
        error=run.error,
    )


@router.post("", response_model=RunResponse, status_code=201)
async def create_run(
    request_data: CreateRunRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("runs:execute")),
) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run = RunService(session).create_run(
            flow_id=request_data.flow_id,
            flow_version=request_data.flow_version,
            inputs=request_data.inputs,
            created_by=auth.user.id,
            idempotency_key=request_data.idempotency_key,
        )
        record_audit(
            session,
            action="run.created",
            target_type="run",
            target_id=run.id,
            user_id=auth.user.id,
            details={"flow_id": run.flow_id, "flow_version": run.flow_version},
            request=request,
        )
        session.commit()
        run_id = run.id

    run_task_manager.start(run_id)
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} was not found")
        return serialize_run(run)


@router.get("", response_model=RunPage)
def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    flow_id: str | None = None,
    created_by: str | None = None,
    sort: Literal["created_at_desc", "created_at_asc", "status_asc"] = "created_at_desc",
) -> RunPage:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        statement = select(Run)
        count_statement = select(func.count()).select_from(Run)
        if status:
            statement = statement.where(Run.status == status)
            count_statement = count_statement.where(Run.status == status)
        if flow_id:
            statement = statement.where(Run.flow_id == flow_id)
            count_statement = count_statement.where(Run.flow_id == flow_id)
        if created_by:
            statement = statement.where(Run.created_by == created_by)
            count_statement = count_statement.where(Run.created_by == created_by)

        order_by = {
            "created_at_desc": Run.created_at.desc(),
            "created_at_asc": Run.created_at.asc(),
            "status_asc": Run.status.asc(),
        }[sort]
        runs = session.scalars(
            statement.order_by(order_by).offset((page - 1) * page_size).limit(page_size)
        ).all()
        total = session.scalar(count_statement) or 0
        return RunPage(
            items=[serialize_run(run) for run in runs],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        return serialize_run(RunService(session).get(run_id))


@router.get("/{run_id}/steps", response_model=list[StepRunResponse])
def get_run_steps(run_id: str) -> list[StepRunResponse]:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        RunService(session).get(run_id)
        steps = session.scalars(
            select(StepRun).where(StepRun.run_id == run_id).order_by(StepRun.id)
        ).all()
        return [
            StepRunResponse(
                id=step.id,
                step_id=step.step_id,
                step_type=step.step_type,
                status=step.status,
                attempt=step.attempt,
                error=step.error,
            )
            for step in steps
        ]


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    request: Request,
    auth: AuthContext = Depends(require_permission("runs:cancel")),
) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run = RunService(session).get(run_id)
        if run.status in {"succeeded", "failed", "cancelled", "timeout"}:
            record_audit(
                session,
                action="run.cancelled",
                target_type="run",
                target_id=run_id,
                user_id=auth.user.id,
                details={"status": run.status},
                request=request,
            )
            session.commit()
            return serialize_run(run)

    run_task_manager.cancel(run_id)
    for _ in range(50):
        await asyncio.sleep(0.05)
        with SessionLocal() as session:
            run = RunService(session).get(run_id)
            if run.status == "cancelled":
                record_audit(
                    session,
                    action="run.cancelled",
                    target_type="run",
                    target_id=run_id,
                    user_id=auth.user.id,
                    details={"status": run.status},
                    request=request,
                )
                session.commit()
                return serialize_run(run)

    with SessionLocal() as session:
        current_run = RunService(session).get(run_id)
        record_audit(
            session,
            action="run.cancelled",
            target_type="run",
            target_id=run_id,
            user_id=auth.user.id,
            details={"status": current_run.status},
            request=request,
        )
        session.commit()
    return serialize_run(current_run)


@router.post("/{run_id}/retry", response_model=RunResponse, status_code=201)
async def retry_run(
    run_id: str,
    request: Request,
    auth: AuthContext = Depends(require_permission("runs:execute")),
) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run = RunService(session).retry(run_id, created_by=auth.user.id)
        record_audit(
            session,
            action="run.retried",
            target_type="run",
            target_id=run.id,
            user_id=auth.user.id,
            details={"source_run_id": run_id},
            request=request,
        )
        session.commit()
        new_run_id = run.id

    run_task_manager.start(new_run_id)
    with SessionLocal() as session:
        run = session.get(Run, new_run_id)
        if run is None:
            raise RunNotFoundError(f"Run {new_run_id} was not found")
        return serialize_run(run)


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    SessionLocal.configure(bind=get_engine())
    start_sequence = int(last_event_id) if last_event_id else 0

    async def event_stream():
        cursor = start_sequence
        with SessionLocal() as session:
            RunService(session).get(run_id)
            while True:
                events = session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.sequence > cursor)
                    .order_by(RunEvent.sequence)
                ).all()
                terminal_event_seen = False
                for event in events:
                    cursor = event.sequence
                    payload = {
                        "type": event.event_type,
                        "stepRunId": event.step_run_id,
                        "data": event.data,
                    }
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                    )
                    if event.event_type in {"run.succeeded", "run.failed", "run.cancelled"}:
                        terminal_event_seen = True

                if terminal_event_seen:
                    break
                await asyncio.sleep(0.1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{run_id}/logs", response_model=list[AgentLogResponse])
def get_run_logs(run_id: str, step_id: str | None = None) -> list[AgentLogResponse]:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        RunService(session).get(run_id)
        statement = (
            select(AgentLogRecord, StepRun)
            .join(StepRun, AgentLogRecord.step_run_id == StepRun.id)
            .where(AgentLogRecord.run_id == run_id)
            .order_by(StepRun.step_id, AgentLogRecord.sequence)
        )
        if step_id is not None:
            statement = statement.where(StepRun.step_id == step_id)
        return [
            AgentLogResponse(
                id=log.id,
                step_run_id=log.step_run_id,
                stream=log.stream,
                sequence=log.sequence,
                content=log.content,
            )
            for log, _step in session.execute(statement).all()
        ]
