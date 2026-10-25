from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

        if self.type == "join" and len(self.depends_on) < 2:
            raise ValueError("A join step must depend on at least two steps")

        return self


class FlowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SchemaVersion = "1.0"
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    inputs: list[FlowInput] = Field(default_factory=list)
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
        return self


def parse_flow_definition(data: dict[str, Any]) -> FlowDefinition:
    """Parse and validate a JSON-compatible Flow definition."""

    return FlowDefinition.model_validate(data)
