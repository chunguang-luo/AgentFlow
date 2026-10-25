import hashlib

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AgentLogRecord, Artifact, StepRun
from app.db.session import SessionLocal, get_engine
from tests.test_run_api import prepare_run


def test_provider_registry_and_mock_health(client):
    providers = client.get("/api/providers")

    assert providers.status_code == 200
    assert [item["name"] for item in providers.json()] == [
        "mock",
        "claude-cli",
        "codex-cli",
    ]

    health = client.post("/api/providers/mock/health-check")
    assert health.status_code == 200
    assert health.json() == {
        "name": "mock",
        "available": True,
        "version": "mock",
        "message": None,
    }


def test_run_logs_and_artifact_download(client):
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        run_id = prepare_run(session)
        step = session.scalars(select(StepRun).where(StepRun.run_id == run_id)).one()
        session.add(
            AgentLogRecord(
                run_id=run_id,
                step_run_id=step.id,
                stream="stdout",
                sequence=1,
                content="provider log\n",
            )
        )

        content = b"downloaded artifact"
        artifact_root = get_settings().artifact_root.expanduser().resolve()
        storage_path = artifact_root / run_id / "report.txt"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        artifact = Artifact(
            run_id=run_id,
            step_run_id=step.id,
            relative_path="report.txt",
            storage_path=str(storage_path),
            content_type="text/plain",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        session.add(artifact)
        session.commit()
        artifact_id = artifact.id

    logs = client.get(f"/api/runs/{run_id}/logs")
    assert logs.status_code == 200
    assert logs.json()[0]["content"] == "provider log\n"

    artifacts = client.get(f"/api/runs/{run_id}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["relative_path"] == "report.txt"

    download = client.get(f"/api/artifacts/{artifact_id}/download")
    assert download.status_code == 200
    assert download.content == b"downloaded artifact"
    assert download.headers["content-type"].startswith("text/plain")
