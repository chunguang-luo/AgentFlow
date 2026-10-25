from typing import Literal

Permission = Literal[
    "flows:read",
    "flows:write",
    "flows:publish",
    "runs:read",
    "runs:execute",
    "runs:cancel",
    "providers:read",
    "providers:check",
    "artifacts:read",
    "audit:read",
]


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "flows:read",
        "flows:write",
        "flows:publish",
        "runs:read",
        "runs:execute",
        "runs:cancel",
        "providers:read",
        "providers:check",
        "artifacts:read",
        "audit:read",
    },
    "editor": {
        "flows:read",
        "flows:write",
        "flows:publish",
        "runs:read",
        "runs:execute",
        "runs:cancel",
        "providers:read",
        "providers:check",
        "artifacts:read",
    },
    "operator": {
        "flows:read",
        "runs:read",
        "runs:execute",
        "runs:cancel",
        "providers:read",
        "artifacts:read",
    },
    "viewer": {
        "flows:read",
        "runs:read",
        "providers:read",
        "artifacts:read",
    },
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())
