import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("user"))
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'editor', 'operator', 'viewer')", name="ck_user_role"),
    )


class Flow(Base):
    __tablename__ = "flows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("flow"))
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    draft_definition: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    current_version: Mapped[int | None] = mapped_column(Integer)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list["FlowVersion"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_flow_status"),
    )


class FlowVersion(Base):
    __tablename__ = "flow_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("flowver"))
    flow_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("flows.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_version: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    flow: Mapped[Flow] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("flow_id", "version", name="uq_flow_version"),)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("run"))
    flow_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("flows.id", ondelete="CASCADE"), index=True
    )
    flow_version: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled', 'timeout')",
            name="ck_run_status",
        ),
        UniqueConstraint("flow_id", "idempotency_key", name="uq_flow_idempotency"),
    )


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("steprun"))
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(100), index=True)
    step_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[Run] = relationship(back_populates="steps")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ready', 'running', 'succeeded', 'failed', "
            "'skipped', 'cancelled', 'timeout')",
            name="ck_step_run_status",
        ),
        UniqueConstraint("run_id", "step_id", "attempt", name="uq_step_run_attempt"),
    )


Index("ix_runs_flow_created", Run.flow_id, Run.created_at)
Index("ix_step_runs_run_step", StepRun.run_id, StepRun.step_id)
