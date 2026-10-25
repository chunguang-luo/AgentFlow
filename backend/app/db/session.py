from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    settings.db_path.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()


def get_session() -> Iterator[Session]:
    SessionLocal.configure(bind=get_engine())
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
