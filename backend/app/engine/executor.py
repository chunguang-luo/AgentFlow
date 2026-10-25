import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AgentLogRecord,
    Artifact,
    FlowVersion,
    Run,
    StepRun,
    utc_now,
)
from app.engine.events import EventRecorder
from app.engine.runs import RunNotFoundError
from app.flows.schema import parse_flow_definition
from app.flows.templating import render_template
from app.providers.base import (
    AgentArtifact,
    AgentLog,
    AgentRequest,
    ProviderExecutionError,
    ProviderRegistry,
)
from app.providers.registry import build_default_provider_registry

TERMINAL_STEP_STATUSES = {"succeeded", "failed", "skipped", "cancelled", "timeout"}


class ExecutionOutcome:
    def __init__(
        self,
        *,
        status: str,
        attempt: int,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        input_snapshot: dict[str, Any] | None = None,
        logs: list[AgentLog] | None = None,
        artifacts: list[AgentArtifact] | None = None,
    ) -> None:
        self.status = status
        self.attempt = attempt
        self.output = output
        self.error = error
        self.input_snapshot = input_snapshot
        self.logs = logs or []
        self.artifacts = artifacts or []


class FlowEngine:
    """Asynchronous DAG executor for Flow versions."""

    def __init__(
        self,
        session: Session,
        *,
        providers: ProviderRegistry | None = None,
        workspace_root: Path | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.session = session
        self.providers = providers or build_default_provider_registry()
        self.events = EventRecorder(session)
        self.workspace_root = (workspace_root or get_settings().workspace_root).resolve()
        self.artifact_root = (artifact_root or get_settings().artifact_root).resolve()

    async def execute(self, run_id: str) -> str:
        run = self.session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} was not found")
        if run.status in {"succeeded", "failed", "cancelled", "timeout"}:
            return run.status

        version = self.session.scalar(
            select(FlowVersion).where(
                FlowVersion.flow_id == run.flow_id,
                FlowVersion.version == run.flow_version,
            )
        )
        if version is None:
            run.status = "failed"
            run.error = f"Flow version {run.flow_version} is unavailable"
            run.finished_at = utc_now()
            self.events.record(
                run_id=run.id,
                event_type="run.failed",
                data={"reason": "missing_flow_version"},
            )
            self.session.commit()
            return run.status

        definition = parse_flow_definition(version.definition)
        step_runs = {
            step_run.step_id: step_run
            for step_run in self.session.scalars(
                select(StepRun).where(StepRun.run_id == run.id)
            ).all()
        }

        run.status = "running"
        run.started_at = run.started_at or utc_now()
        run.finished_at = None
        run.error = None
        self.events.record(run_id=run.id, event_type="run.started")

        running_tasks: dict[str, asyncio.Task[ExecutionOutcome]] = {}
        cancelled_internally = False

        def step_output_map() -> dict[str, Any]:
            return {
                step_id: step_run.output
                for step_id, step_run in step_runs.items()
                if step_run.status == "succeeded"
            }

        def dependencies_are_terminal(step_id: str) -> bool:
            step = next(item for item in definition.steps if item.id == step_id)
            return all(
                step_runs[dependency].status in TERMINAL_STEP_STATUSES
                for dependency in step.depends_on
            )

        def can_execute(step_id: str) -> bool | None:
            step = next(item for item in definition.steps if item.id == step_id)
            if not dependencies_are_terminal(step_id):
                return None

            successful = [
                dependency
                for dependency in step.depends_on
                if step_runs[dependency].status == "succeeded"
                and step_runs[dependency].output.get("condition", True) is not False
            ]
            if len(successful) == len(step.depends_on):
                return True
            return bool(
                step.type == "join" and successful and step.config.get("ignoreSkipped", False)
            )

        def remaining_step_ids() -> list[str]:
            return [
                step_id
                for step_id, step_run in step_runs.items()
                if step_run.status not in TERMINAL_STEP_STATUSES
            ]

        try:
            while True:
                remaining = remaining_step_ids()
                newly_skipped = False
                for step_id in remaining:
                    if step_id in running_tasks:
                        continue
                    eligibility = can_execute(step_id)
                    if eligibility is True:
                        step_run = step_runs[step_id]
                        step_run.status = "ready"
                        self.events.record(
                            run_id=run.id,
                            event_type="step.ready",
                            step_run_id=step_run.id,
                            data={"step_id": step_id},
                        )
                        step_run.status = "running"
                        step_run.started_at = utc_now()
                        step_run.finished_at = None
                        step_run.error = None
                        self.events.record(
                            run_id=run.id,
                            event_type="step.started",
                            step_run_id=step_run.id,
                            data={"step_id": step_id, "attempt": step_run.attempt},
                        )
                        running_tasks[step_id] = asyncio.create_task(
                            self._execute_step(
                                definition=next(
                                    item for item in definition.steps if item.id == step_id
                                ),
                                step_run_id=step_run.id,
                                run_id=run.id,
                                initial_attempt=step_run.attempt,
                                inputs=run.inputs,
                                previous_outputs=step_output_map(),
                            )
                        )
                    elif eligibility is False:
                        step_run = step_runs[step_id]
                        step_run.status = "skipped"
                        step_run.finished_at = utc_now()
                        self.events.record(
                            run_id=run.id,
                            event_type="step.skipped",
                            step_run_id=step_run.id,
                            data={"step_id": step_id, "reason": "dependency_not_succeeded"},
                        )
                        newly_skipped = True

                if not running_tasks:
                    if newly_skipped:
                        continue
                    if remaining_step_ids():
                        for step_id in remaining_step_ids():
                            step_runs[step_id].status = "skipped"
                            step_runs[step_id].finished_at = utc_now()
                        self.events.record(
                            run_id=run.id,
                            event_type="run.failed",
                            data={"reason": "scheduler_deadlock"},
                        )
                        run.status = "failed"
                        run.error = "No runnable steps remain"
                        run.finished_at = utc_now()
                        self.session.commit()
                        return run.status
                    break

                done, _pending = await asyncio.wait(
                    running_tasks.values(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    step_id = next(key for key, value in running_tasks.items() if value == task)
                    del running_tasks[step_id]
                    step_run = step_runs[step_id]
                    outcome = task.result()
                    step_run.attempt = outcome.attempt
                    step_run.input_snapshot = outcome.input_snapshot
                    step_run.output = self._persist_side_effects(
                        run_id=run.id,
                        step_run=step_run,
                        outcome=outcome,
                    )
                    step_run.error = outcome.error
                    step_run.status = outcome.status
                    step_run.finished_at = utc_now()

                    event_type = {
                        "succeeded": "step.succeeded",
                        "failed": "step.failed",
                        "timeout": "step.timeout",
                        "cancelled": "step.cancelled",
                    }.get(outcome.status, "step.skipped")
                    self.events.record(
                        run_id=run.id,
                        event_type=event_type,
                        step_run_id=step_run.id,
                        data={
                            "step_id": step_id,
                            "attempt": outcome.attempt,
                            **({"error": outcome.error} if outcome.error else {}),
                        },
                    )

                    if (
                        outcome.status in {"failed", "timeout"}
                        and definition.execution.failure_strategy == "fail_fast"
                    ):
                        cancelled_internally = True
                        break

                if cancelled_internally:
                    await self._cancel_running_tasks(running_tasks)
                    for step_run in step_runs.values():
                        if step_run.status == "running":
                            step_run.status = "cancelled"
                            step_run.error = "Cancelled because another step failed"
                            step_run.finished_at = utc_now()
                        elif step_run.status in {"pending", "ready"}:
                            step_run.status = "skipped"
                            step_run.finished_at = utc_now()
                    break

            final_status = "succeeded"
            if any(
                step_run.status in {"failed", "timeout", "cancelled"}
                for step_run in step_runs.values()
            ):
                final_status = "failed"

            outputs = step_output_map()
            analysis_steps = [step for step in definition.steps if step.type == "analysis"]
            result: dict[str, Any]
            if analysis_steps and analysis_steps[-1].id in outputs:
                result = {
                    "analysis": outputs[analysis_steps[-1].id],
                    "steps": outputs,
                }
            else:
                result = {"steps": outputs}

            run.status = final_status
            run.result = result
            run.finished_at = utc_now()
            self.events.record(
                run_id=run.id,
                event_type=f"run.{'succeeded' if final_status == 'succeeded' else 'failed'}",
                data={"step_count": len(step_runs)},
            )
            self.session.commit()
            return run.status

        except asyncio.CancelledError:
            await self._cancel_running_tasks(running_tasks)
            for step_run in step_runs.values():
                if step_run.status == "running":
                    step_run.status = "cancelled"
                    step_run.error = "Run cancelled"
                    step_run.finished_at = utc_now()
                elif step_run.status in {"pending", "ready"}:
                    step_run.status = "skipped"
                    step_run.finished_at = utc_now()

            run.status = "cancelled"
            run.finished_at = utc_now()
            self.events.record(run_id=run.id, event_type="run.cancelled")
            self.session.commit()
            raise

    async def _cancel_running_tasks(self, tasks: dict[str, asyncio.Task[ExecutionOutcome]]) -> None:
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        tasks.clear()

    async def _execute_step(
        self,
        *,
        definition: Any,
        step_run_id: str,
        run_id: str,
        initial_attempt: int,
        inputs: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> ExecutionOutcome:
        step = definition
        config = step.config
        attempt = initial_attempt
        max_retries = int(config.get("maxRetries", 0))
        if max_retries < 0:
            return ExecutionOutcome(
                status="failed",
                attempt=attempt,
                error="maxRetries must not be negative",
            )

        timeout_seconds = float(config.get("timeoutSeconds", 900))
        if timeout_seconds <= 0:
            return ExecutionOutcome(
                status="failed",
                attempt=attempt,
                error="timeoutSeconds must be greater than zero",
            )

        snapshot: dict[str, Any] = {"attempt": attempt}
        step_id = str(getattr(definition, "id", "step"))
        step_workspace_base = self.workspace_root / run_id / step_id
        step_artifact_base = self.artifact_root / run_id / step_id
        working_dir = step_workspace_base / f"attempt-{attempt}"
        artifact_dir = step_artifact_base / f"attempt-{attempt}"
        working_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        try:
            if step.type == "template":
                rendered = render_template(
                    str(config["template"]),
                    inputs=inputs,
                    steps=previous_outputs,
                )
                snapshot["template"] = config["template"]
                return ExecutionOutcome(
                    status="succeeded",
                    attempt=attempt,
                    output={"text": rendered},
                    input_snapshot=snapshot,
                )

            if step.type == "condition":
                expression = str(config["expression"])
                rendered = render_template(
                    "{% if " + expression + " %}true{% else %}false{% endif %}",
                    inputs=inputs,
                    steps=previous_outputs,
                )
                snapshot["expression"] = expression
                return ExecutionOutcome(
                    status="succeeded",
                    attempt=attempt,
                    output={"condition": rendered == "true"},
                    input_snapshot=snapshot,
                )

            if step.type == "parallel":
                branch_ids = config["branches"]
                snapshot["branches"] = branch_ids
                return ExecutionOutcome(
                    status="succeeded",
                    attempt=attempt,
                    output={
                        "branches": {
                            branch_id: previous_outputs.get(branch_id)
                            for branch_id in branch_ids
                            if branch_id in previous_outputs
                        }
                    },
                    input_snapshot=snapshot,
                )

            if step.type == "join":
                snapshot["depends_on"] = step.depends_on
                return ExecutionOutcome(
                    status="succeeded",
                    attempt=attempt,
                    output={
                        "inputs": {
                            dependency: previous_outputs.get(dependency)
                            for dependency in step.depends_on
                        }
                    },
                    input_snapshot=snapshot,
                )

            if step.type in {"input", "analysis"} and "provider" not in config:
                prompt_template = str(config.get("prompt", ""))
                rendered = render_template(prompt_template, inputs=inputs, steps=previous_outputs)
                snapshot["prompt"] = prompt_template
                return ExecutionOutcome(
                    status="succeeded",
                    attempt=attempt,
                    output={"text": rendered},
                    input_snapshot=snapshot,
                )

            provider_name = str(config["provider"])
            prompt_template = str(config["prompt"])
            prompt = render_template(prompt_template, inputs=inputs, steps=previous_outputs)
            snapshot.update({"provider": provider_name, "prompt": prompt})

            while True:
                try:
                    result = await asyncio.wait_for(
                        self.providers.get(provider_name).execute(
                            AgentRequest(
                                execution_id=step_run_id,
                                provider=provider_name,
                                prompt=prompt,
                                attempt=attempt,
                                timeout_seconds=timeout_seconds,
                                config=config,
                                working_dir=working_dir,
                                artifact_dir=artifact_dir,
                            )
                        ),
                        timeout=timeout_seconds,
                    )
                    output = {"text": result.text, "json": result.data}
                    artifact_metadata = [self._artifact_metadata(item) for item in result.artifacts]
                    if artifact_metadata:
                        output["artifacts"] = artifact_metadata
                    return ExecutionOutcome(
                        status="succeeded",
                        attempt=attempt,
                        output=output,
                        input_snapshot=snapshot,
                        logs=result.logs,
                        artifacts=result.artifacts,
                    )
                except TimeoutError:
                    if attempt <= max_retries:
                        attempt += 1
                        working_dir = step_workspace_base / f"attempt-{attempt}"
                        artifact_dir = step_artifact_base / f"attempt-{attempt}"
                        working_dir.mkdir(parents=True, exist_ok=True)
                        artifact_dir.mkdir(parents=True, exist_ok=True)
                        snapshot["attempt"] = attempt
                        continue
                    return ExecutionOutcome(
                        status="timeout",
                        attempt=attempt,
                        error=f"Step timed out after {timeout_seconds} seconds",
                        input_snapshot=snapshot,
                    )
                except ProviderExecutionError as exc:
                    if attempt <= max_retries:
                        attempt += 1
                        working_dir = step_workspace_base / f"attempt-{attempt}"
                        artifact_dir = step_artifact_base / f"attempt-{attempt}"
                        working_dir.mkdir(parents=True, exist_ok=True)
                        artifact_dir.mkdir(parents=True, exist_ok=True)
                        snapshot["attempt"] = attempt
                        continue
                    output = None
                    if exc.logs or exc.artifacts:
                        output = {
                            "artifacts": [self._artifact_metadata(item) for item in exc.artifacts]
                        }
                    return ExecutionOutcome(
                        status="timeout" if exc.timed_out else "failed",
                        attempt=attempt,
                        output=output,
                        error=str(exc),
                        input_snapshot=snapshot,
                        logs=exc.logs,
                        artifacts=exc.artifacts,
                    )
                except Exception as exc:
                    if attempt <= max_retries:
                        attempt += 1
                        working_dir = step_workspace_base / f"attempt-{attempt}"
                        artifact_dir = step_artifact_base / f"attempt-{attempt}"
                        working_dir.mkdir(parents=True, exist_ok=True)
                        artifact_dir.mkdir(parents=True, exist_ok=True)
                        snapshot["attempt"] = attempt
                        continue
                    return ExecutionOutcome(
                        status="failed",
                        attempt=attempt,
                        error=str(exc),
                        input_snapshot=snapshot,
                    )
        except Exception as exc:
            return ExecutionOutcome(
                status="failed",
                attempt=attempt,
                error=str(exc),
                input_snapshot=snapshot,
            )

    def _persist_side_effects(
        self,
        *,
        run_id: str,
        step_run: StepRun,
        outcome: ExecutionOutcome,
    ) -> dict[str, Any] | None:
        self.session.execute(
            delete(AgentLogRecord).where(AgentLogRecord.step_run_id == step_run.id)
        )
        self.session.execute(delete(Artifact).where(Artifact.step_run_id == step_run.id))

        for sequence, log in enumerate(outcome.logs, start=1):
            self.session.add(
                AgentLogRecord(
                    run_id=run_id,
                    step_run_id=step_run.id,
                    stream=log.stream,
                    sequence=sequence,
                    content=log.content,
                )
            )

        artifact_metadata: list[dict[str, Any]] = []
        for artifact in outcome.artifacts:
            self.session.add(
                Artifact(
                    run_id=run_id,
                    step_run_id=step_run.id,
                    relative_path=artifact.relative_path,
                    storage_path=str(artifact.storage_path),
                    content_type=artifact.content_type,
                    size_bytes=artifact.size_bytes,
                    sha256=artifact.sha256,
                )
            )
            artifact_metadata.append(self._artifact_metadata(artifact))

        output = dict(outcome.output or {})
        if artifact_metadata:
            output["artifacts"] = artifact_metadata
        return output

    @staticmethod
    def _artifact_metadata(artifact: AgentArtifact) -> dict[str, Any]:
        return {
            "relativePath": artifact.relative_path,
            "contentType": artifact.content_type,
            "sizeBytes": artifact.size_bytes,
            "sha256": artifact.sha256,
        }
