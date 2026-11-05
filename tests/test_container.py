import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import container_run


def test_run_workspace_is_an_independent_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "AGENTS.md").write_text(
        "# Environment and tool use\nWindows\n# Run output\nPreserve rules",
        encoding="utf-8",
    )
    (source / "task.prompt").write_text("original", encoding="utf-8")
    result = container_run.prepare_workspace(source, tmp_path / "run")
    (result / "task.prompt").write_text("changed", encoding="utf-8")
    assert (source / "task.prompt").read_text(encoding="utf-8") == "original"
    instructions = (result / "AGENTS.md").read_text(encoding="utf-8")
    assert "/workspace" in instructions
    assert "# Run output\nPreserve rules" in instructions


def test_container_command_mounts_only_run_workspace(tmp_path: Path) -> None:
    command = container_run.container_command(
        tmp_path, "run-test", "isolated-network", "secret"
    )
    assert command.count("--mount") == 1
    assert f"type=bind,src={tmp_path},dst=/workspace" in command
    assert "--privileged" not in command
    assert "isolated-network" in command
    assert "HTTPS_PROXY=http://gateway:3128" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command


def test_rejects_workspace_root_junction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(os.path, "isjunction", lambda path: Path(path) == source)
    with pytest.raises(ValueError, match="link or junction"):
        container_run.prepare_workspace(source, tmp_path / "run")


def test_cleanup_reports_docker_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        container_run.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 1, "", "daemon unavailable"
        ),
    )
    assert container_run.cleanup_container("long-horizon-test") is False
    assert "long-horizon-test" in capsys.readouterr().err


def test_cleanup_accepts_container_already_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        container_run.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 1, "", "Error: No such container: long-horizon-test"
        ),
    )
    assert container_run.cleanup_container("long-horizon-test") is True


def test_sokoban_workspace_copies_task_and_instructions(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "sokoban_workspace"
    workspace = container_run.prepare_workspace(source, tmp_path / "run")
    assert "Sokoban" in (workspace / "task.prompt").read_text(encoding="utf-8")
    instructions = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "/workspace" in instructions
    assert "run-version" in instructions
    assert (workspace / "src" / "sokoban.py").is_file()
    assert int((workspace / ".run-version").read_text(encoding="utf-8")) == 0
