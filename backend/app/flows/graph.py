from collections import defaultdict, deque
from typing import Protocol


class GraphValidationError(ValueError):
    """Raised when the Step graph is not a valid DAG."""


class StepLike(Protocol):
    id: str
    depends_on: list[str]


def validate_dag(steps: list[StepLike]) -> None:
    step_ids = [step.id for step in steps]
    if len(step_ids) != len(set(step_ids)):
        raise GraphValidationError("Step IDs must be unique")

    id_set = set(step_ids)
    for step in steps:
        for dependency in step.depends_on:
            if dependency not in id_set:
                raise GraphValidationError(
                    f"Step {step.id!r} depends on unknown step {dependency!r}"
                )
            if dependency == step.id:
                raise GraphValidationError(f"Step {step.id!r} cannot depend on itself")

    in_degree = {step.id: len(step.depends_on) for step in steps}
    dependents: dict[str, list[str]] = defaultdict(list)
    for step in steps:
        for dependency in step.depends_on:
            dependents[dependency].append(step.id)

    queue = deque(step_id for step_id, degree in in_degree.items() if degree == 0)
    visited_count = 0
    while queue:
        current = queue.popleft()
        visited_count += 1
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if visited_count != len(steps):
        cyclic = sorted(step_id for step_id, degree in in_degree.items() if degree > 0)
        raise GraphValidationError(f"Flow contains a dependency cycle: {', '.join(cyclic)}")
