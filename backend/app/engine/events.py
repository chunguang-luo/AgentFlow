from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RunEvent


class EventRecorder:
    """Persist ordered execution events for a run."""

    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        *,
        run_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        step_run_id: str | None = None,
    ) -> RunEvent:
        current = self.session.scalar(
            select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
        )
        event = RunEvent(
            run_id=run_id,
            sequence=(current or 0) + 1,
            event_type=event_type,
            step_run_id=step_run_id,
            data=data or {},
        )
        self.session.add(event)
        self.session.flush()
        return event
