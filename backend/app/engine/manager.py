import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.engine.executor import FlowEngine

logger = logging.getLogger(__name__)


class RunTaskManager:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, run_id: str) -> None:
        if run_id in self._tasks and not self._tasks[run_id].done():
            return

        self._tasks[run_id] = asyncio.create_task(self._execute_managed(run_id))

    async def _execute_managed(self, run_id: str) -> None:
        session = self._session_factory()
        try:
            await FlowEngine(session).execute(run_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            session.rollback()
            logger.exception("Run execution failed unexpectedly")
        finally:
            session.close()
            self._tasks.pop(run_id, None)

    def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await asyncio.shield(task)


run_task_manager = RunTaskManager()
