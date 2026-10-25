from typing import Any

from jinja2 import Environment, StrictUndefined, meta
from jinja2.exceptions import SecurityError, TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment

MAX_TEMPLATE_LENGTH = 100_000
MAX_RENDER_LENGTH = 1_000_000
ALLOWED_ROOTS = frozenset({"inputs", "steps", "env"})


class FlowTemplateError(ValueError):
    """Raised when a Flow template is invalid or unsafe."""


def create_template_environment() -> Environment:
    return ImmutableSandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render_template(
    template: str,
    *,
    inputs: dict[str, Any],
    steps: dict[str, Any],
    env: dict[str, Any] | None = None,
) -> str:
    if not isinstance(template, str):
        raise FlowTemplateError("Template must be a string")
    if len(template) > MAX_TEMPLATE_LENGTH:
        raise FlowTemplateError(f"Template exceeds {MAX_TEMPLATE_LENGTH} characters")

    environment = create_template_environment()
    try:
        parsed = environment.parse(template)
        variables = meta.find_undeclared_variables(parsed)
    except TemplateError as exc:
        raise FlowTemplateError(f"Invalid template syntax: {exc}") from exc

    unknown_variables = sorted(variables - ALLOWED_ROOTS)
    if unknown_variables:
        raise FlowTemplateError(
            f"Template variables must start with inputs, steps, or env; "
            f"found: {', '.join(unknown_variables)}"
        )

    allowed_env = env or {}
    try:
        rendered = environment.from_string(template).render(
            inputs=inputs,
            steps=steps,
            env=allowed_env,
        )
    except SecurityError as exc:
        raise FlowTemplateError(f"Template access denied: {exc}") from exc
    except TemplateError as exc:
        raise FlowTemplateError(f"Template rendering failed: {exc}") from exc

    if len(rendered) > MAX_RENDER_LENGTH:
        raise FlowTemplateError(f"Rendered template exceeds {MAX_RENDER_LENGTH} characters")
    return rendered
