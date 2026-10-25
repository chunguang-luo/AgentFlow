import pytest

from app.flows.templating import FlowTemplateError, render_template


def test_renders_only_flow_context_roots() -> None:
    result = render_template(
        "{{ inputs.repo_path }} / {{ steps.architecture.json.field }} / {{ env.API_MODE }}",
        inputs={"repo_path": "service"},
        steps={"architecture": {"json": {"field": "clean"}}},
        env={"API_MODE": "test"},
    )

    assert result == "service / clean / test"


def test_rejects_unknown_root_variable() -> None:
    with pytest.raises(FlowTemplateError, match="Template variables must start with"):
        render_template("{{ secrets.token }}", inputs={}, steps={})


def test_rejects_sandbox_escape() -> None:
    with pytest.raises(FlowTemplateError, match="Template access denied"):
        render_template("{{ ''.__class__ }}", inputs={}, steps={})


def test_rejects_undefined_values() -> None:
    with pytest.raises(FlowTemplateError, match="Template rendering failed"):
        render_template("{{ inputs.missing }}", inputs={}, steps={})
