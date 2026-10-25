import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FlowVersion, Run, StepRun, utc_now
from app.engine.events import EventRecorder
from app.flows.schema import parse_flow_definition, validate_flow_inputs


class RunNotFoundError(LookupError):
    pass


class RunValidationError(ValueError):
    pass


class RunService:
    def __init__(self, session: Session):
        self.session = session
        self.events = EventRecorder(session)

    def create_run(
        self,
        *,
        flow_id: str,
        inputs: dict[str, Any],
        created_by: str,
        flow_version: int | None = None,
        idempotency_key: str | None = None,
    ) -> Run:
        existing = None
        if idempotency_key:
            existing = self.session.scalar(
                select(Run).where(
                    Run.flow_id == flow_id,
                    Run.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.inputs != inputs:
                    raise RunValidationError(
                        "An existing idempotency key has different flow inputs"
                    )
                return existing

        version_number = flow_version
        if version_number is None:
            version = self.session.scalar(
                select(FlowVersion)
                .where(FlowVersion.flow_id == flow_id)
                .order_by(FlowVersion.version.desc())
                .limit(1)
            )
        else:
            version = self.session.scalar(
                select(FlowVersion).where(
                    FlowVersion.flow_id == flow_id,
                    FlowVersion.version == version_number,
                )
            )

        if version is None:
            raise RunNotFoundError(f"No runnable version found for flow {flow_id}")

        definition = parse_flow_definition(version.definition)
        try:
            normalized_inputs = validate_flow_inputs(definition.inputs, inputs)
        except ValueError as exc:
            raise RunValidationError(str(exc)) from exc

        run = Run(
            flow_id=flow_id,
            flow_version=version.version,
            idempotency_key=idempotency_key,
            status="pending",
            inputs=normalized_inputs,
            created_by=created_by,
        )
        self.session.add(run)
        self.session.flush()

        for step in definition.steps:
            self.session.add(
                StepRun(
                    run_id=run.id,
                    step_id=step.id,
                    step_type=step.type,
                    status="pending",
                    attempt=1,
                )
            )

        self.events.record(
            run_id=run.id,
            event_type="run.created",
            data={"flow_id": flow_id, "flow_version": version.version},
        )
        self.session.flush()
        return run

    def get(self, run_id: str) -> Run:
        run = self.session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} was not found")
        return run

    def retry(self, run_id: str, *, created_by: str) -> Run:
        source = self.get(run_id)
        if source.status not in {"failed", "cancelled", "timeout"}:
            raise RunValidationError("Only terminal failed runs can be retried")

        return self.create_run(
            flow_id=source.flow_id,
            flow_version=source.flow_version,
            inputs=source.inputs,
            created_by=created_by,
            idempotency_key=f"{source.id}:retry:{uuid.uuid4().hex[:8]}",
        )


def recover_interrupted_runs(session: Session) -> int:
    """Mark runs left active by a process crash as retryable terminal runs."""

    recorder = EventRecorder(session)
    runs = session.scalars(select(Run).where(Run.status == "running")).all()
    recovered = 0
    for run in runs:
        steps = session.scalars(select(StepRun).where(StepRun.run_id == run.id)).all()
        for step in steps:
            if step.status in {"pending", "ready"}:
                step.status = "skipped"
                step.finished_at = utc_now()
            elif step.status == "running":
                step.status = "cancelled"
                step.error = "Execution interrupted by service restart"
                step.finished_at = utc_now()

        run.status = "failed"
        run.error = "Execution interrupted by service restart"
        run.finished_at = utc_now()
        recorder.record(
            run_id=run.id,
            event_type="run.interrupted",
            data={"reason": "service_restart"},
        )
        recovered += 1

    if recovered:
        session.flush()
    return recovered
