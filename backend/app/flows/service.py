from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Flow, FlowVersion, new_id
from app.flows.schema import FlowDefinition, parse_flow_definition


class FlowNotFoundError(LookupError):
    pass


class FlowService:
    """Persistence boundary for draft Flow definitions and immutable versions."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, definition: FlowDefinition, *, owner_id: str) -> Flow:
        definition = parse_flow_definition(definition.model_dump(mode="json"))
        flow = Flow(
            id=new_id("flow"),
            name=definition.name,
            description=definition.description,
            status="draft",
            draft_definition=definition.model_dump(mode="json"),
            owner_id=owner_id,
        )
        self.session.add(flow)
        self.session.flush()
        return flow

    def get(self, flow_id: str) -> Flow:
        flow = self.session.get(Flow, flow_id)
        if flow is None:
            raise FlowNotFoundError(f"Flow {flow_id} was not found")
        return flow

    def update_draft(self, flow_id: str, definition: FlowDefinition) -> Flow:
        flow = self.get(flow_id)
        definition = parse_flow_definition(definition.model_dump(mode="json"))
        flow.name = definition.name
        flow.description = definition.description
        flow.draft_definition = definition.model_dump(mode="json")
        flow.status = "draft"
        self.session.flush()
        return flow

    def publish(self, flow_id: str, *, published_by: str) -> FlowVersion:
        flow = self.get(flow_id)
        if not flow.draft_definition:
            raise ValueError(f"Flow {flow_id} has no draft definition")

        definition = parse_flow_definition(flow.draft_definition)
        next_version = (flow.current_version or 0) + 1
        version = FlowVersion(
            flow_id=flow.id,
            version=next_version,
            definition=definition.model_dump(mode="json"),
            schema_version=definition.schema_version,
            created_by=published_by,
        )
        self.session.add(version)
        flow.current_version = next_version
        flow.status = "published"
        self.session.flush()
        return version

    def export(
        self,
        flow_id: str,
        *,
        version: int | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        flow = self.get(flow_id)
        if draft or version is None and flow.current_version is None:
            if not flow.draft_definition:
                raise ValueError(f"Flow {flow_id} has no draft definition")
            return flow.draft_definition

        selected_version = version or flow.current_version
        statement = select(FlowVersion).where(
            FlowVersion.flow_id == flow.id,
            FlowVersion.version == selected_version,
        )
        flow_version = self.session.scalar(statement)
        if flow_version is None:
            raise FlowNotFoundError(f"Flow {flow_id} version {selected_version} was not found")
        return flow_version.definition

    def import_definition(self, data: dict[str, Any], *, owner_id: str) -> Flow:
        definition = parse_flow_definition(data)
        return self.create(definition, owner_id=owner_id)
