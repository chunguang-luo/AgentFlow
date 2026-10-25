import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import AgentLogRecord, Artifact
from app.engine.executor import FlowEngine
from app.providers.base import ProviderError, ProviderExecutionError, ProviderRegistry
from app.providers.cli import CLIProvider, claude_command, codex_command
from app.providers.subprocess import SubprocessRunner
from tests.test_engine import create_executable_run


def make_script(path: Path, body: str) -> str:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return str(path)


def make_runner(tmp_path: Path, **overrides) -> SubprocessRunner:
    values = {
        "env_allowlist": ["PATH"],
        "max_output_bytes": 1_000_000,
        "max_log_bytes": 100_000,
        "max_artifacts_per_step": 10,
        "max_artifact_bytes": 1_000_000,
    }
    values.update(overrides)
    return SubprocessRunner(**values)


def make_provider(executable: str, runner: SubprocessRunner) -> CLIProvider:
    return CLIProvider(
        name="claude-cli",
        executable=executable,
        command_builder=claude_command(executable),
        runner=runner,
    )


def request(tmp_path: Path, **overrides):
    values = {
        "execution_id": "step-1",
        "provider": "claude-cli",
        "prompt": "Analyze repository",
        "attempt": 1,
        "timeout_seconds": 5,
        "working_dir": tmp_path / "work",
        "artifact_dir": tmp_path / "artifacts",
        "config": {},
    }
    values.update(overrides)
    return type("Request", (), values)


def test_claude_cli_provider_collects_logs_and_artifacts(tmp_path):
    executable = make_script(
        tmp_path / "agent",
        """
mkdir -p artifacts
printf 'report body' > artifacts/report.txt
printf 'log line\\n' >&2
printf '{"result":"analysis complete","model":"fake"}'
""",
    )
    provider = make_provider(executable, make_runner(tmp_path))
    agent_request = request(tmp_path)

    result = asyncio.run(provider.execute(agent_request))

    assert result.text == "analysis complete"
    assert result.data == {"result": "analysis complete", "model": "fake"}
    assert [log.content for log in result.logs] == [
        '{"result":"analysis complete","model":"fake"}',
        "log line\n",
    ]
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.relative_path == "artifacts/report.txt"
    assert artifact.content_type == "text/plain"
    assert artifact.size_bytes == len(b"report body")
    assert artifact.sha256 == hashlib.sha256(b"report body").hexdigest()
    assert artifact.storage_path.read_text() == "report body"


def test_cli_provider_timeout_terminates_process(tmp_path):
    executable = make_script(tmp_path / "agent", "sleep 5")
    provider = make_provider(
        executable,
        make_runner(tmp_path),
    )
    agent_request = request(tmp_path, timeout_seconds=0.05)

    with pytest.raises(ProviderExecutionError, match="timed out") as exc_info:
        asyncio.run(provider.execute(agent_request))

    assert exc_info.value.timed_out is True


def test_cli_provider_cancellation_terminates_process(tmp_path):
    executable = make_script(
        tmp_path / "agent",
        """
printf 'started\\n' >&2
sleep 2
mkdir artifacts
printf 'late' > artifacts/late.txt
""",
    )
    provider = make_provider(executable, make_runner(tmp_path))
    agent_request = request(tmp_path)

    async def cancel_provider():
        task = asyncio.create_task(provider.execute(agent_request))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_provider())
    assert not (tmp_path / "work" / "artifacts" / "late.txt").exists()


def test_cli_provider_failure_preserves_logs_and_artifacts(tmp_path):
    executable = make_script(
        tmp_path / "agent",
        """
mkdir artifacts
printf 'partial' > artifacts/partial.txt
printf 'stdout before failure\\n' >&1
printf 'stderr before failure\\n' >&2
exit 7
""",
    )
    provider = make_provider(executable, make_runner(tmp_path))
    agent_request = request(tmp_path)

    with pytest.raises(ProviderExecutionError, match="exit code 7") as exc_info:
        asyncio.run(provider.execute(agent_request))

    assert exc_info.value.exit_code == 7
    assert [log.content for log in exc_info.value.logs] == [
        "stdout before failure\n",
        "stderr before failure\n",
    ]
    assert exc_info.value.artifacts[0].relative_path == "artifacts/partial.txt"


def test_cli_provider_environment_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTFLOW_TEST_SECRET", "secret-value")
    executable = make_script(
        tmp_path / "agent",
        """
if [ -n "$AGENTFLOW_TEST_SECRET" ]; then
  printf 'secret leaked' >&2
  exit 1
fi
printf '{"result":"safe"}'
""",
    )
    provider = make_provider(executable, make_runner(tmp_path))
    result = asyncio.run(provider.execute(request(tmp_path)))

    assert result.text == "safe"


def test_cli_provider_health(tmp_path):
    executable = make_script(tmp_path / "agent", "printf 'agent version 1.2.3'")
    provider = make_provider(executable, make_runner(tmp_path))

    health = asyncio.run(provider.check_health())

    assert health.available is True
    assert health.version == "agent version 1.2.3"


def test_cli_provider_parses_jsonl_events():
    provider = CLIProvider(
        name="codex-cli",
        executable="codex",
        command_builder=lambda _request: ["codex"],
    )
    stdout = "\n".join(
        [
            json.dumps({"type": "event", "message": "first"}),
            json.dumps({"type": "result", "result": "final"}),
        ]
    )

    text, data = provider.parse_output(stdout)

    assert text == "first\nfinal"
    assert data["type"] == "result"


def test_codex_command_uses_noninteractive_git_check_override():
    command = codex_command("codex")(type("Request", (), {"prompt": "Run"}))

    assert command[:4] == ["codex", "exec", "--skip-git-repo-check", "--json"]


def test_cli_provider_parses_codex_item_events():
    provider = CLIProvider(
        name="codex-cli",
        executable="codex",
        command_builder=lambda _request: ["codex"],
    )
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "OK"},
                }
            ),
            json.dumps({"type": "turn.completed", "usage": {}}),
        ]
    )

    text, data = provider.parse_output(stdout)

    assert text == "OK"
    assert data["type"] == "turn.completed"


def test_engine_persists_cli_logs_and_artifacts(execution_session, tmp_path):
    executable = make_script(
        tmp_path / "agent",
        """
mkdir artifacts
printf 'engine artifact' > artifacts/result.txt
printf 'engine log\\n' >&2
printf '{"result":"engine output"}'
""",
    )
    registry = ProviderRegistry()
    registry.register(
        make_provider(
            executable,
            make_runner(tmp_path),
        )
    )
    data = {
        "name": "CLI flow",
        "inputs": [],
        "steps": [
            {
                "id": "cli",
                "name": "CLI",
                "type": "agent",
                "config": {"prompt": "Run", "provider": "claude-cli"},
            }
        ],
    }
    run = create_executable_run(execution_session, data)

    engine = FlowEngine(
        execution_session,
        providers=registry,
        workspace_root=tmp_path / "workspaces",
        artifact_root=tmp_path / "artifact-store",
    )
    status = asyncio.run(engine.execute(run.id))

    assert status == "succeeded"
    logs = execution_session.scalars(select(AgentLogRecord)).all()
    artifacts = execution_session.scalars(select(Artifact)).all()
    assert [log.content for log in logs] == [
        '{"result":"engine output"}',
        "engine log\n",
    ]
    assert artifacts[0].relative_path == "artifacts/result.txt"
    assert artifacts[0].storage_path == str(
        tmp_path / "artifact-store" / run.id / "cli" / "attempt-1" / "artifacts" / "result.txt"
    )


def test_subprocess_output_is_limited(tmp_path):
    executable = make_script(tmp_path / "agent", "printf '0123456789\\n'")
    provider = make_provider(
        executable,
        make_runner(
            tmp_path,
            max_output_bytes=5,
            max_log_bytes=3,
        ),
    )

    result = asyncio.run(provider.execute(request(tmp_path)))

    assert result.text == "01234"
    assert result.logs[0].content == "012"


def test_artifact_patterns_cannot_escape_workspace(tmp_path):
    runner = make_runner(tmp_path)
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    agent_request = request(tmp_path, config={"artifactPatterns": ["../**/*"]})

    with pytest.raises(ProviderError, match="relative to the step workspace"):
        runner.collect_artifacts(agent_request, working_dir, tmp_path / "artifacts")
