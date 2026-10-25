import pytest
from pydantic import ValidationError

from app.flows.schema import parse_flow_definition


def valid_definition() -> dict:
    return {
        "schema_version": "1.0",
        "name": "Repository analysis",
        "description": "Analyze a repository from two angles.",
        "inputs": [{"name": "repo_path", "type": "string"}],
        "steps": [
            {
                "id": "architecture",
                "name": "Architecture analysis",
                "type": "agent",
                "depends_on": [],
                "config": {"prompt": "Analyze {{ inputs.repo_path }}", "provider": "mock"},
            },
            {
                "id": "risk",
                "name": "Risk analysis",
                "type": "agent",
                "depends_on": [],
                "config": {"prompt": "Find risks", "provider": "mock"},
            },
            {
                "id": "report",
                "name": "Final report",
                "type": "analysis",
                "depends_on": ["architecture", "risk"],
                "config": {"prompt": "Write a report"},
            },
        ],
    }


def test_valid_flow_definition_parses() -> None:
    definition = parse_flow_definition(valid_definition())

    assert definition.name == "Repository analysis"
    assert [step.id for step in definition.steps] == [
        "architecture",
        "risk",
        "report",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda flow: flow["steps"].append({**flow["steps"][0]}), "Step IDs must be unique"),
        (
            lambda flow: flow["steps"][2]["depends_on"].append("missing"),
            "depends on unknown step",
        ),
        (
            lambda flow: flow["steps"][0]["depends_on"].append("report"),
            "dependency cycle",
        ),
        (
            lambda flow: flow["steps"][0]["config"].pop("provider"),
            "missing config keys: provider",
        ),
    ],
)
def test_invalid_flow_definitions_are_rejected(mutation, message: str) -> None:
    data = valid_definition()
    mutation(data)

    with pytest.raises(ValidationError, match=message):
        parse_flow_definition(data)


def test_join_requires_multiple_dependencies() -> None:
    data = valid_definition()
    data["steps"][2]["type"] = "join"
    data["steps"][2]["depends_on"] = ["architecture"]

    with pytest.raises(ValidationError, match="join step must depend"):
        parse_flow_definition(data)
