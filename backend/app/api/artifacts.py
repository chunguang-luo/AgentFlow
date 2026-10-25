from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import require_permission
from app.core.config import get_settings
from app.core.errors import APIError
from app.db.models import Artifact, Run
from app.db.session import SessionLocal, get_engine
from app.engine.runs import RunNotFoundError, RunService

router = APIRouter(
    prefix="/api",
    tags=["artifacts"],
    dependencies=[Depends(require_permission("artifacts:read"))],
)


class ArtifactResponse(BaseModel):
    id: str
    run_id: str
    step_run_id: str
    relative_path: str
    content_type: str
    size_bytes: int
    sha256: str


def serialize_artifact(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        run_id=artifact.run_id,
        step_run_id=artifact.step_run_id,
        relative_path=artifact.relative_path,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
    )


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactResponse])
def list_run_artifacts(run_id: str) -> list[ArtifactResponse]:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        RunService(session).get(run_id)
        artifacts = session.scalars(
            select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.relative_path)
        ).all()
        return [serialize_artifact(artifact) for artifact in artifacts]


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str) -> FileResponse:
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise APIError(
                status_code=404,
                code="artifact_not_found",
                message=f"Artifact {artifact_id} was not found",
            )

        run = session.get(Run, artifact.run_id)
        if run is None:
            raise RunNotFoundError(f"Run {artifact.run_id} was not found")

        storage_path = Path(artifact.storage_path).expanduser().resolve()
        artifact_root = get_settings().artifact_root.expanduser().resolve()
        if (
            not storage_path.is_relative_to(artifact_root)
            or storage_path.is_symlink()
            or not storage_path.is_file()
        ):
            raise APIError(
                status_code=404,
                code="artifact_not_available",
                message="Artifact file is unavailable",
            )

        return FileResponse(
            storage_path,
            media_type=artifact.content_type,
            filename=storage_path.name,
        )
