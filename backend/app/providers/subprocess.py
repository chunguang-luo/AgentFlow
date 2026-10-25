import asyncio
import contextlib
import hashlib
import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.providers.base import (
    AgentArtifact,
    AgentLog,
    AgentRequest,
    ProviderError,
    ProviderExecutionError,
)

DEFAULT_ARTIFACT_PATTERNS = ("artifacts/**/*",)


@dataclass(frozen=True, slots=True)
class SubprocessResult:
    exit_code: int
    stdout: str
    stderr: str
    logs: list[AgentLog]
    artifacts: list[AgentArtifact]


class SubprocessRunner:
    """Run a trusted CLI command with resource and path boundaries."""

    def __init__(
        self,
        *,
        env_allowlist: list[str],
        max_output_bytes: int,
        max_log_bytes: int,
        max_artifacts_per_step: int,
        max_artifact_bytes: int,
    ) -> None:
        self.env_allowlist = set(env_allowlist)
        self.max_output_bytes = max_output_bytes
        self.max_log_bytes = max_log_bytes
        self.max_artifacts_per_step = max_artifacts_per_step
        self.max_artifact_bytes = max_artifact_bytes

    async def run(self, command: list[str], request: AgentRequest) -> SubprocessResult:
        if not command:
            raise ProviderError("Provider command must not be empty")
        if request.working_dir is None or request.artifact_dir is None:
            raise ProviderError("Provider execution requires working and artifact directories")

        working_dir = request.working_dir.expanduser().resolve()
        artifact_dir = request.artifact_dir.expanduser().resolve()
        working_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=working_dir,
                env=self._environment(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                start_new_session=True,
                limit=max(64 * 1024, self.max_output_bytes + 1),
            )
        except (FileNotFoundError, PermissionError) as exc:
            raise ProviderError(f"Unable to start provider executable: {exc}") from exc

        stdout_task = asyncio.create_task(
            self._read_stream(process.stdout, "stdout", self.max_output_bytes)
        )
        stderr_task = asyncio.create_task(
            self._read_stream(process.stderr, "stderr", self.max_output_bytes)
        )

        try:
            stdout_chunks, stderr_chunks = await asyncio.wait_for(
                asyncio.shield(asyncio.gather(stdout_task, stderr_task)),
                timeout=request.timeout_seconds,
            )
            exit_code = await process.wait()
        except TimeoutError:
            await self._terminate(process, stdout_task, stderr_task)
            raise ProviderExecutionError(
                f"Provider command timed out after {request.timeout_seconds} seconds",
                exit_code=process.returncode,
                timed_out=True,
                logs=[*stdout_task.result(), *stderr_task.result()],
            ) from None
        except asyncio.CancelledError:
            await self._terminate(process, stdout_task, stderr_task)
            raise

        stdout_logs, stdout_bytes = stdout_chunks
        stderr_logs, stderr_bytes = stderr_chunks
        logs = [*stdout_logs, *stderr_logs]
        artifacts = self.collect_artifacts(request, working_dir, artifact_dir)

        if exit_code != 0:
            raise ProviderExecutionError(
                f"Provider command failed with exit code {exit_code}",
                exit_code=exit_code,
                logs=logs,
                artifacts=artifacts,
            )

        return SubprocessResult(
            exit_code=exit_code,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            logs=logs,
            artifacts=artifacts,
        )

    def _environment(self) -> dict[str, str]:
        environment = {name: os.environ[name] for name in self.env_allowlist if name in os.environ}
        environment.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
        return environment

    async def _read_stream(
        self,
        stream: asyncio.StreamReader | None,
        name: str,
        max_output_bytes: int,
    ) -> tuple[list[AgentLog], bytes]:
        if stream is None:
            return [], b""

        chunks: list[bytes] = []
        logs: list[AgentLog] = []
        captured = 0
        logged = 0
        while True:
            line = await stream.readline()
            if not line:
                break
            if captured < max_output_bytes:
                allowed = line[: max_output_bytes - captured]
                chunks.append(allowed)
                captured += len(allowed)
            if logged < self.max_log_bytes:
                allowed_log = line[: self.max_log_bytes - logged]
                logs.append(AgentLog(stream=name, content=allowed_log.decode("utf-8", "replace")))
                logged += len(allowed_log)

        return logs, b"".join(chunks)

    def collect_artifacts(
        self,
        request: AgentRequest,
        working_dir: Path,
        artifact_dir: Path,
    ) -> list[AgentArtifact]:
        patterns = request.config.get("artifactPatterns", list(DEFAULT_ARTIFACT_PATTERNS))
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise ProviderError("artifactPatterns must be a list of glob patterns")
        if any(Path(pattern).is_absolute() or ".." in Path(pattern).parts for pattern in patterns):
            raise ProviderError("artifactPatterns must be relative to the step workspace")

        artifacts: dict[str, AgentArtifact] = {}
        total_bytes = 0
        for pattern in patterns:
            for source in working_dir.glob(pattern):
                if not source.is_file() or source.is_symlink():
                    continue
                resolved_source = source.resolve()
                try:
                    resolved_source.relative_to(working_dir)
                except ValueError as exc:
                    raise ProviderError("Artifact path escaped the step workspace") from exc

                relative_path = resolved_source.relative_to(working_dir).as_posix()
                if relative_path in artifacts:
                    continue
                if len(artifacts) >= self.max_artifacts_per_step:
                    raise ProviderError(
                        f"Step produced more than {self.max_artifacts_per_step} artifacts"
                    )

                size = resolved_source.stat().st_size
                if total_bytes + size > self.max_artifact_bytes:
                    raise ProviderError("Step artifacts exceed the configured size limit")

                destination = artifact_dir / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    destination.unlink()
                shutil.copyfile(resolved_source, destination)

                digest = hashlib.sha256()
                with resolved_source.open("rb") as artifact_file:
                    for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                        digest.update(chunk)

                artifacts[relative_path] = AgentArtifact(
                    relative_path=relative_path,
                    storage_path=destination,
                    content_type=self._content_type(relative_path),
                    size_bytes=size,
                    sha256=digest.hexdigest(),
                )
                total_bytes += size

        return sorted(artifacts.values(), key=lambda item: item.relative_path)

    @staticmethod
    def _content_type(relative_path: str) -> str:
        content_type, _ = mimetypes.guess_type(relative_path)
        return content_type or "application/octet-stream"

    @staticmethod
    async def _terminate(
        process: asyncio.subprocess.Process,
        stdout_task: asyncio.Task[tuple[list[AgentLog], bytes]],
        stderr_task: asyncio.Task[tuple[list[AgentLog], bytes]],
    ) -> None:
        if process.returncode is None and process.pid > 0:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(process.pid), 15)
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(os.getpgid(process.pid), 9)
                await process.wait()

        for task in (stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
