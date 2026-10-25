import json
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings
from app.providers.base import (
    AgentRequest,
    AgentResult,
    ProviderError,
    ProviderExecutionError,
    ProviderHealth,
)
from app.providers.subprocess import SubprocessRunner


class CLIProvider:
    """Base adapter for non-interactive Agent CLI tools."""

    def __init__(
        self,
        *,
        name: str,
        executable: str,
        command_builder: Callable[[AgentRequest], list[str]],
        version_args: tuple[str, ...] = ("--version",),
        runner: SubprocessRunner | None = None,
    ) -> None:
        self.name = name
        self.executable = executable
        self.command_builder = command_builder
        self.version_args = version_args
        settings = get_settings()
        self.runner = runner or SubprocessRunner(
            env_allowlist=settings.agent_env_allowlist,
            max_output_bytes=settings.max_agent_output_bytes,
            max_log_bytes=settings.max_agent_log_bytes,
            max_artifacts_per_step=settings.max_artifacts_per_step,
            max_artifact_bytes=settings.max_artifact_bytes,
        )

    async def execute(self, request: AgentRequest) -> AgentResult:
        command = self.command_builder(request)
        try:
            result = await self.runner.run(command, request)
        except ProviderExecutionError:
            raise
        except ProviderError:
            raise

        text, data = self.parse_output(result.stdout)
        return AgentResult(
            text=text,
            data=data,
            logs=result.logs,
            artifacts=result.artifacts,
        )

    async def check_health(self) -> ProviderHealth:
        settings = get_settings()
        health_working_dir = settings.workspace_root.expanduser().resolve() / ".health" / self.name
        health_artifact_dir = settings.artifact_root.expanduser().resolve() / ".health" / self.name
        request = AgentRequest(
            execution_id=f"{self.name}-health",
            provider=self.name,
            prompt="",
            attempt=1,
            timeout_seconds=5,
            config={"artifactPatterns": []},
            working_dir=health_working_dir,
            artifact_dir=health_artifact_dir,
        )
        try:
            result = await self.runner.run([self.executable, *self.version_args], request)
        except ProviderExecutionError as exc:
            return ProviderHealth(
                provider=self.name,
                available=False,
                message=str(exc),
            )
        except ProviderError as exc:
            return ProviderHealth(
                provider=self.name,
                available=False,
                message=str(exc),
            )

        return ProviderHealth(
            provider=self.name,
            available=True,
            version=result.stdout.strip().splitlines()[0] if result.stdout.strip() else None,
        )

    def parse_output(self, stdout: str) -> tuple[str, dict[str, Any]]:
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            return "", {}

        parsed: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict):
                continue
            parsed.append(value)

        if not parsed:
            return stdout.strip(), {}

        primary = parsed[-1]
        messages: list[str] = []
        for item in parsed:
            message = self._extract_text(item)
            if message and (not messages or messages[-1] != message):
                messages.append(message)
        text = "\n".join(messages)
        return text, primary

    @staticmethod
    def _extract_text(value: dict[str, Any]) -> str:
        for key in ("result", "text", "message", "content"):
            item = value.get(key)
            if isinstance(item, str) and item:
                return item
        nested = value.get("data")
        if isinstance(nested, dict):
            for key in ("result", "text", "message", "content"):
                item = nested.get(key)
                if isinstance(item, str) and item:
                    return item
        event_item = value.get("item")
        if isinstance(event_item, dict) and event_item.get("type") in {
            "agent_message",
            "message",
        }:
            item = event_item.get("text")
            if isinstance(item, str) and item:
                return item
        return ""


def claude_command(executable: str) -> Callable[[AgentRequest], list[str]]:
    def build(request: AgentRequest) -> list[str]:
        return [
            executable,
            "--print",
            request.prompt,
            "--output-format",
            "json",
        ]

    return build


def codex_command(executable: str) -> Callable[[AgentRequest], list[str]]:
    def build(request: AgentRequest) -> list[str]:
        return [
            executable,
            "exec",
            "--skip-git-repo-check",
            "--json",
            request.prompt,
        ]

    return build


def build_claude_provider(executable: str | None = None, runner: SubprocessRunner | None = None):
    settings = get_settings()
    return CLIProvider(
        name="claude-cli",
        executable=executable or settings.claude_cli_path,
        command_builder=claude_command(executable or settings.claude_cli_path),
        runner=runner,
    )


def build_codex_provider(executable: str | None = None, runner: SubprocessRunner | None = None):
    settings = get_settings()
    return CLIProvider(
        name="codex-cli",
        executable=executable or settings.codex_cli_path,
        command_builder=codex_command(executable or settings.codex_cli_path),
        runner=runner,
    )
