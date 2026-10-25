import importlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_settings_cache
from app.db.session import dispose_engine


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "agentflow.db"
    monkeypatch.setenv("AGENTFLOW_DB_PATH", str(db_path))
    monkeypatch.setenv("AGENTFLOW_ENV", "test")
    monkeypatch.setenv("AGENTFLOW_CORS_ORIGINS", "[]")

    reset_settings_cache()
    dispose_engine()

    import app.main

    importlib.reload(app.main)
    with TestClient(app.main.app) as test_client:
        yield test_client

    reset_settings_cache()
    dispose_engine()
