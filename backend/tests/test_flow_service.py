import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, User
from app.flows.schema import parse_flow_definition
from app.flows.service import FlowService


@pytest.fixture
def service():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(id="owner", username="owner", password_hash="hash", role="editor")
        session.add(owner)
        session.flush()
        yield FlowService(session), owner.id
    Base.metadata.drop_all(engine)


def definition_data(name: str = "First") -> dict:
    return {
        "schema_version": "1.0",
        "name": name,
        "inputs": [],
        "steps": [
            {
                "id": "analyze",
                "name": "Analyze",
                "type": "agent",
                "config": {"prompt": "Analyze", "provider": "mock"},
            }
        ],
    }


def test_flow_versions_are_immutable(service) -> None:
    flow_service, owner_id = service
    flow = flow_service.create(parse_flow_definition(definition_data()), owner_id=owner_id)

    first_version = flow_service.publish(flow.id, published_by=owner_id)
    assert first_version.version == 1

    updated = parse_flow_definition(definition_data("Second"))
    flow_service.update_draft(flow.id, updated)
    second_version = flow_service.publish(flow.id, published_by=owner_id)
    assert second_version.version == 2

    assert flow_service.export(flow.id)["name"] == "Second"
    assert flow_service.export(flow.id, version=1)["name"] == "First"


def test_import_and_export_round_trip(service) -> None:
    flow_service, owner_id = service
    data = definition_data()

    flow = flow_service.import_definition(data, owner_id=owner_id)

    exported = flow_service.export(flow.id, draft=True)
    assert parse_flow_definition(exported).model_dump() == parse_flow_definition(data).model_dump()
