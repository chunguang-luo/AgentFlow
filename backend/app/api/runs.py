import asyncio
import json
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import AgentLogRecord, Run, RunEvent, StepRun
from app.db.session import SessionLocal, get_engine
from app.engine.manager import run_task_manager
from app.engine.runs import RunNotFoundError, RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])


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
async def create_run(request: CreateRunRequest) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run = RunService(session).create_run(
            flow_id=request.flow_id,
            flow_version=request.flow_version,
            inputs=request.inputs,
            created_by="local-development-user",
            idempotency_key=request.idempotency_key,
        )
        session.commit()
        run_id = run.id

    run_task_manager.start(run_id)
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} was not found")
        return serialize_run(run)


@router.get("", response_model=list[RunResponse])
def list_runs() -> list[RunResponse]:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        runs = session.scalars(select(Run).order_by(Run.created_at.desc()).limit(100)).all()
        return [serialize_run(run) for run in runs]


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
async def cancel_run(run_id: str) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run = RunService(session).get(run_id)
        if run.status in {"succeeded", "failed", "cancelled", "timeout"}:
            return serialize_run(run)

    run_task_manager.cancel(run_id)
    for _ in range(50):
        await asyncio.sleep(0.05)
        with SessionLocal() as session:
            run = RunService(session).get(run_id)
            if run.status == "cancelled":
                return serialize_run(run)

    return serialize_run(run)


@router.post("/{run_id}/retry", response_model=RunResponse, status_code=201)
async def retry_run(run_id: str) -> RunResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run = RunService(session).retry(run_id, created_by="local-development-user")
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
