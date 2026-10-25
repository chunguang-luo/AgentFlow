import asyncio

from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import SessionLocal, get_engine
from app.engine.executor import FlowEngine
from app.engine.runs import RunService
from app.flows.schema import parse_flow_definition
from app.flows.service import FlowService


def prepare_run(session: Session, *, required_input: bool = False) -> str:
    owner = User(id="owner", username="owner", password_hash="hash", role="editor")
    session.add(owner)
    session.flush()
    flow_service = FlowService(session)
    definition = {
        "name": "API flow",
        "inputs": ([{"name": "mode", "type": "string"}] if required_input else []),
        "steps": [
            {
                "id": "analyze",
                "name": "Analyze",
                "type": "agent",
                "config": {"prompt": "Analyze", "provider": "mock"},
            }
        ],
    }
    flow = flow_service.create(parse_flow_definition(definition), owner_id="owner")
    flow_service.publish(flow.id, published_by="owner")
    if required_input:
        session.commit()
        return flow.id
    run = RunService(session).create_run(
        flow_id=flow.id,
        inputs={} if required_input else {},
        created_by="owner",
    )
    session.commit()
    if not required_input:
        asyncio.run(FlowEngine(session).execute(run.id))
    return run.id


def test_run_detail_steps_and_sse(client):
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run_id = prepare_run(session)

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"

    steps = client.get(f"/api/runs/{run_id}/steps")
    assert steps.status_code == 200
    assert steps.json()[0]["step_id"] == "analyze"
    assert steps.json()[0]["status"] == "succeeded"

    events = client.get(f"/api/runs/{run_id}/events")
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: run.started" in events.text
    assert "event: run.succeeded" in events.text


def test_create_run_rejects_missing_required_input(client):
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        flow_id = prepare_run(session, required_input=True)

    response = client.post("/api/runs", json={"flow_id": flow_id, "inputs": {}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "run_validation_error"


def test_unknown_run_returns_error_contract(client):
    response = client.get("/api/runs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"
