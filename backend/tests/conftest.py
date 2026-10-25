import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import reset_settings_cache
from app.db.models import Base, User
from app.db.session import dispose_engine, get_engine


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "agentflow.db"
    monkeypatch.setenv("AGENTFLOW_DB_PATH", str(db_path))
    monkeypatch.setenv("AGENTFLOW_ENV", "test")
    monkeypatch.setenv("AGENTFLOW_CORS_ORIGINS", "[]")

    reset_settings_cache()
    dispose_engine()
    Base.metadata.create_all(bind=get_engine())

    import app.main

    importlib.reload(app.main)
    with TestClient(app.main.app) as test_client:
        yield test_client

    reset_settings_cache()
    Base.metadata.drop_all(bind=get_engine())
    dispose_engine()


@pytest.fixture
def execution_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(id="owner", username="owner", password_hash="hash", role="editor")
        session.add(owner)
        session.flush()
        yield session
    Base.metadata.drop_all(engine)
