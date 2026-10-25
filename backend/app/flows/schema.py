import json
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.flows.graph import validate_dag

SchemaVersion = Literal["1.0"]
InputType = Literal["string", "number", "boolean", "json"]
StepType = Literal[
    "input",
    "template",
    "agent",
    "condition",
    "parallel",
    "join",
    "analysis",
]


class FlowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
    label: str | None = None
    type: InputType
    required: bool = True
    default: Any = None
    description: str | None = None


ExecutionFailureStrategy = Literal["fail_fast", "continue"]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_strategy: ExecutionFailureStrategy = Field(
        default="fail_fast",
        validation_alias=AliasChoices("failure_strategy", "failureStrategy"),
    )


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    type: StepType
    depends_on: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("depends_on must not contain duplicate step IDs")
        return value

    @model_validator(mode="after")
    def validate_config(self) -> "Step":
        match self.type:
            case "agent":
                required = ("prompt", "provider")
            case "template":
                required = ("template",)
            case "condition":
                required = ("expression",)
            case "analysis":
                required = ("prompt",)
            case "parallel":
                required = ("branches",)
            case _:
                required = ()

        missing = [key for key in required if key not in self.config]
        if missing:
            raise ValueError(f"Step {self.id!r} is missing config keys: {', '.join(missing)}")

        if self.type == "parallel" and len(self.config["branches"]) < 2:
            raise ValueError("A parallel step must declare at least two branches")

        if self.type in {"agent", "analysis"} and not isinstance(self.config.get("prompt"), str):
            raise ValueError(f"Step {self.id!r} prompt must be a string")

        if self.type == "agent" and not isinstance(self.config.get("provider"), str):
            raise ValueError(f"Step {self.id!r} provider must be a string")

        if self.type == "template" and not isinstance(self.config.get("template"), str):
            raise ValueError(f"Step {self.id!r} template must be a string")

        if self.type == "condition" and not isinstance(self.config.get("expression"), str):
            raise ValueError(f"Step {self.id!r} expression must be a string")

        if self.type == "parallel":
            branches = self.config["branches"]
            if not isinstance(branches, list) or not all(
                isinstance(branch, str) for branch in branches
            ):
                raise ValueError("A parallel step branches value must be a list of step IDs")

        if self.type == "join" and len(self.depends_on) < 2:
            raise ValueError("A join step must depend on at least two steps")

        return self


class FlowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SchemaVersion = "1.0"
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    inputs: list[FlowInput] = Field(default_factory=list)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    steps: list[Step] = Field(min_length=1)

    @field_validator("inputs")
    @classmethod
    def validate_input_names(cls, value: list[FlowInput]) -> list[FlowInput]:
        names = [item.name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("Flow input names must be unique")
        return value

    @model_validator(mode="after")
    def validate_definition(self) -> "FlowDefinition":
        validate_dag(self.steps)
        step_ids = {step.id for step in self.steps}
        for step in (item for item in self.steps if item.type == "parallel"):
            branches = set(step.config["branches"])
            if len(branches) != len(step.config["branches"]):
                raise ValueError(f"Parallel step {step.id!r} branches must be unique")
            if not branches.issubset(step.depends_on):
                raise ValueError(
                    f"Parallel step {step.id!r} branches must be declared in depends_on"
                )
            if not branches.issubset(step_ids):
                raise ValueError(f"Parallel step {step.id!r} has an unknown branch")
        return self


def parse_flow_definition(data: dict[str, Any]) -> FlowDefinition:
    """Parse and validate a JSON-compatible Flow definition."""

    return FlowDefinition.model_validate(data)


def validate_flow_inputs(definitions: list[FlowInput], values: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize run inputs against a Flow definition."""

    unknown = sorted(set(values) - {item.name for item in definitions})
    if unknown:
        raise ValueError(f"Unknown flow inputs: {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    for item in definitions:
        if item.name not in values and item.default is not None:
            normalized[item.name] = item.default
            continue
        if item.name not in values:
            if item.required:
                raise ValueError(f"Required flow input is missing: {item.name}")
            continue

        value = values[item.name]
        if item.type == "string" and not isinstance(value, str):
            raise ValueError(f"Flow input {item.name} must be a string")
        if item.type == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError(f"Flow input {item.name} must be a number")
        if item.type == "boolean" and not isinstance(value, bool):
            raise ValueError(f"Flow input {item.name} must be a boolean")
        if item.type == "json":
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"Flow input {item.name} must be JSON serializable") from exc

        normalized[item.name] = value

    return normalized
