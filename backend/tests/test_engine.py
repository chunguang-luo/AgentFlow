import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import RunEvent, StepRun, utc_now
from app.engine.executor import FlowEngine
from app.engine.manager import RunTaskManager
from app.engine.runs import RunService, recover_interrupted_runs
from app.flows.schema import parse_flow_definition
from app.flows.service import FlowService


def definition() -> dict:
    return {
        "name": "Engine flow",
        "inputs": [{"name": "mode", "type": "string", "required": False, "default": "deep"}],
        "steps": [
            {
                "id": "first",
                "name": "First",
                "type": "agent",
                "config": {
                    "prompt": "Result for {{ inputs.mode }}",
                    "provider": "mock",
                    "mock": {"output": "first-output"},
                },
            },
            {
                "id": "second",
                "name": "Second",
                "type": "agent",
                "depends_on": ["first"],
                "config": {
                    "prompt": "{{ steps.first.text }} plus second",
                    "provider": "mock",
                    "mock": {"output": "second-output"},
                },
            },
            {
                "id": "report",
                "name": "Report",
                "type": "analysis",
                "depends_on": ["second"],
                "config": {"prompt": "Report from {{ steps.second.text }}"},
            },
        ],
    }


def create_executable_run(session: Session, data: dict | None = None):
    flows = FlowService(session)
    flow = flows.create(parse_flow_definition(data or definition()), owner_id="owner")
    flows.publish(flow.id, published_by="owner")
    run = RunService(session).create_run(flow_id=flow.id, inputs={}, created_by="owner")
    session.commit()
    return run


def test_sequential_run_and_analysis(execution_session):
    run = create_executable_run(execution_session)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "succeeded"
    execution_session.refresh(run)
    assert run.result["steps"]["first"]["text"] == "first-output"
    assert run.result["analysis"]["text"] == "Report from second-output"

    events = execution_session.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.sequence)
    ).all()
    assert events[0].event_type == "run.created"
    assert events[-1].event_type == "run.succeeded"
    assert len({event.sequence for event in events}) == len(events)


def test_mock_provider_retry(execution_session):
    data = definition()
    data["steps"][0]["config"]["mock"]["failUntilAttempt"] = 1
    data["steps"][0]["config"]["maxRetries"] = 1
    run = create_executable_run(execution_session, data)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "succeeded"
    step = execution_session.scalar(select(StepRun).where(StepRun.run_id == run.id))
    assert step.attempt == 2
    assert step.output["text"] == "first-output"


def test_fail_fast_cancels_parallel_step(execution_session):
    data = definition()
    data["steps"][0]["config"]["mock"] = {"failUntilAttempt": 2}
    data["steps"][1]["config"]["mock"] = {"delaySeconds": 0.1}
    run = create_executable_run(execution_session, data)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "failed"
    statuses = {
        step.step_id: step.status
        for step in execution_session.scalars(select(StepRun).where(StepRun.run_id == run.id))
    }
    assert statuses == {
        "first": "failed",
        "second": "skipped",
        "report": "skipped",
    }


def test_continue_failure_strategy(execution_session):
    data = definition()
    data["execution"] = {"failureStrategy": "continue"}
    data["steps"][0]["config"]["mock"] = {"failUntilAttempt": 2}
    data["steps"][1] = {
        "id": "independent",
        "name": "Independent",
        "type": "agent",
        "config": {"prompt": "Independent", "provider": "mock"},
    }
    data["steps"][2]["depends_on"] = ["first"]
    run = create_executable_run(execution_session, data)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "failed"
    statuses = {
        step.step_id: step.status
        for step in execution_session.scalars(select(StepRun).where(StepRun.run_id == run.id))
    }
    assert statuses["first"] == "failed"
    assert statuses["independent"] == "succeeded"
    assert statuses["report"] == "skipped"


def test_timeout(execution_session):
    data = definition()
    data["steps"][0]["config"].update({"timeoutSeconds": 0.01, "mock": {"delaySeconds": 0.2}})
    run = create_executable_run(execution_session, data)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "failed"
    step = execution_session.scalar(select(StepRun).where(StepRun.run_id == run.id))
    assert step.status == "timeout"
    assert step.error is not None


def test_cancel_running_run(execution_session):
    data = definition()
    data["steps"][0]["config"]["mock"] = {"delaySeconds": 0.5}
    run = create_executable_run(execution_session, data)

    async def cancel_while_running():
        engine = FlowEngine(execution_session)
        task = asyncio.create_task(engine.execute(run.id))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_while_running())
    execution_session.expire_all()
    assert run.status == "cancelled"
    assert all(
        step.status in {"cancelled", "skipped"}
        for step in execution_session.scalars(select(StepRun).where(StepRun.run_id == run.id))
    )


def test_condition_and_join_ignore_skipped(execution_session):
    data = definition()
    data["inputs"][0]["default"] = "quick"
    data["steps"] = [
        {
            "id": "yes",
            "name": "Yes",
            "type": "condition",
            "config": {"expression": "inputs.mode == 'quick'"},
        },
        {
            "id": "no",
            "name": "No",
            "type": "condition",
            "config": {"expression": "inputs.mode == 'deep'"},
        },
        {
            "id": "join",
            "name": "Join",
            "type": "join",
            "depends_on": ["yes", "no"],
            "config": {"ignoreSkipped": True},
        },
    ]
    run = create_executable_run(execution_session, data)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "succeeded"
    steps = {
        step.step_id: step
        for step in execution_session.scalars(select(StepRun).where(StepRun.run_id == run.id))
    }
    assert steps["yes"].output == {"condition": True}
    assert steps["no"].output == {"condition": False}
    assert steps["join"].status == "succeeded"


def test_parallel_branches_execute_and_aggregate(execution_session):
    data = definition()
    data["steps"] = [
        {
            "id": "left",
            "name": "Left",
            "type": "agent",
            "config": {
                "prompt": "Left",
                "provider": "mock",
                "mock": {"delaySeconds": 0.03, "output": "left-output"},
            },
        },
        {
            "id": "right",
            "name": "Right",
            "type": "agent",
            "config": {
                "prompt": "Right",
                "provider": "mock",
                "mock": {"delaySeconds": 0.03, "output": "right-output"},
            },
        },
        {
            "id": "merge",
            "name": "Merge",
            "type": "parallel",
            "depends_on": ["left", "right"],
            "config": {"branches": ["left", "right"]},
        },
    ]
    run = create_executable_run(execution_session, data)

    status = asyncio.run(FlowEngine(execution_session).execute(run.id))

    assert status == "succeeded"
    merge = execution_session.scalar(
        select(StepRun).where(StepRun.run_id == run.id, StepRun.step_id == "merge")
    )
    assert merge.output == {
        "branches": {
            "left": {"text": "left-output", "json": {}},
            "right": {"text": "right-output", "json": {}},
        }
    }


def test_run_task_manager(execution_session):
    run = create_executable_run(execution_session)

    async def execute_with_manager():
        manager = RunTaskManager(session_factory=sessionmaker(bind=execution_session.bind))
        manager.start(run.id)
        await manager.wait(run.id)

    asyncio.run(execute_with_manager())
    execution_session.refresh(run)
    assert run.status == "succeeded"


def test_create_run_is_idempotent(execution_session):
    data = definition()
    data["inputs"] = []
    run = create_executable_run(execution_session, data)
    run.idempotency_key = "stable-key"
    execution_session.commit()
    service = RunService(execution_session)
    same_run = service.create_run(
        flow_id=run.flow_id,
        inputs={},
        created_by="owner",
        idempotency_key="stable-key",
    )

    assert same_run.id == run.id


def test_service_restart_recovery(execution_session):
    run = create_executable_run(execution_session)
    run.status = "running"
    run.started_at = utc_now()
    step = execution_session.scalar(select(StepRun).where(StepRun.run_id == run.id))
    step.status = "running"
    execution_session.commit()

    recovered = recover_interrupted_runs(execution_session)
    execution_session.commit()

    assert recovered == 1
    execution_session.refresh(run)
    execution_session.refresh(step)
    assert run.status == "failed"
    assert run.error == "Execution interrupted by service restart"
    assert step.status == "cancelled"
