import ctypes
import json
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import supervisor
from supervisor import supervise

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("fake_pi.py")


def run_case(tmp_path: Path, mode: str, limit: float = 0.35) -> tuple[dict, list[dict]]:
    result = supervise(
        [sys.executable, str(FAKE), mode],
        "test task",
        limit,
        tmp_path,
        grace_seconds=0.5,
    )
    records = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return result, records


def test_starts_agent_in_experiment_workspace(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "complete", 3)
    assert result["status"] == "settled"
    cwd = next(r["cwd"] for r in records if r.get("type") == "test_cwd")
    assert Path(cwd) == ROOT / "experiment_workspace"
    assert (Path(cwd) / "task.prompt").is_file()
    assert (Path(cwd) / "AGENTS.md").is_file()


def test_finished_run_keeps_events_and_reports_completion(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "complete", 3)
    assert result["status"] == "settled"
    assert any(r.get("type") == "agent_settled" for r in records)


def test_timeout_requests_abort_before_forced_termination(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "abort")
    assert result["status"] == "timeout"
    assert result["termination"] == "graceful"
    assert any(r.get("command") == "abort" and r.get("success") for r in records)


def test_hung_run_uses_forced_termination(tmp_path: Path) -> None:
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        result, records = run_case(tmp_path, "hang")
        assert result["status"] == "timeout"
        assert result["termination"] == "forced"
        pid = next(r["pid"] for r in records if r.get("type") == "test_child")
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        dll.OpenProcess.restype = wintypes.HANDLE
        dll.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        dll.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = dll.OpenProcess(0x100000, False, pid)
        if handle:
            try:
                assert dll.WaitForSingleObject(handle, 3000) == 0
            finally:
                dll.CloseHandle(handle)
        assert sentinel.poll() is None
    finally:
        sentinel.terminate()
        sentinel.wait(timeout=5)


def test_startup_failure_is_not_reported_as_completion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, _ = run_case(tmp_path, "exit", 3)
    assert "launcher: test startup failure" in capsys.readouterr().err
    assert result["status"] == "startup_error"
    assert result["prompt_submitted_at_utc"] is None
    assert result["launcher_exit_code"] == 2


def test_runtime_failure_is_not_reported_as_startup_failure(tmp_path: Path) -> None:
    result, _ = run_case(tmp_path, "crash", 3)
    assert result["status"] == "run_error"
    assert result["prompt_submitted_at_utc"] is not None


def test_rejects_invalid_time_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        supervise([sys.executable, str(FAKE), "hang"], "task", 0, tmp_path)


@pytest.mark.parametrize("thinking", ["high", "off"])
@pytest.mark.parametrize(("cleanup_ok", "expected_code"), [(True, 0), (False, 1)])
def test_launcher_uses_isolated_container_and_model_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_ok: bool,
    expected_code: int,
    thinking: str,
) -> None:
    seen = []
    prompts = []

    class Guard:
        def __init__(self, name: str, token: str, digest: str, mode: str) -> None:
            assert mode == thinking
            self.network = "verified-network"

        def start(self) -> None:
            pass

        def close(self) -> bool:
            return True

    def fake_supervise(
        command: list[str], prompt: str, limit_seconds: float, run_dir: Path
    ) -> dict:
        seen.extend(command)
        prompts.append(prompt)
        return {"status": "settled"}

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "supervise", fake_supervise)

    def prepare_workspace(source: Path, run: Path) -> Path:
        workspace = run / "workspace"
        workspace.mkdir()
        (workspace / "task.prompt").write_text(
            "Assignment content: build the profile.", encoding="utf-8"
        )
        return workspace

    monkeypatch.setattr(
        supervisor.container_run, "prepare_workspace", prepare_workspace
    )
    monkeypatch.setattr(
        supervisor.ollama_model,
        "prepare_model",
        lambda model, context: {
            "model": model,
            "model_digest": "digest",
            "allocated_context": 131072,
        },
    )
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(
        supervisor.container_run, "cleanup_container", lambda name: cleanup_ok
    )
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--thinking", thinking])
    assert supervisor.main() == expected_code
    if not cleanup_ok:
        outcomes = list((tmp_path / "supervisor-runs").glob("*/outcome.json"))
        assert (
            json.loads(outcomes[0].read_text(encoding="utf-8"))["container_cleanup"]
            == "failed"
        )
    assert seen[:2] == ["docker", "run"]
    assert "verified-network" in seen
    assert f"THINKING_MODE={thinking}" in seen
    assert not any("PI_REPETITION" in value for value in seen)
    model_info = list((tmp_path / "supervisor-runs").glob("*/model.json"))
    assert (
        json.loads(model_info[0].read_text(encoding="utf-8"))["model"] == "qwen-custom"
    )
    assert json.loads(model_info[0].read_text(encoding="utf-8"))["thinking"] is (
        thinking == "high"
    )
    assert "Assignment content: build the profile." in prompts[0]
    assert "Read task.prompt" not in prompts[0]


@pytest.mark.parametrize("content", [None, "   "])
def test_missing_or_empty_assignment_stops_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None
) -> None:
    def prepare_workspace(source: Path, run: Path) -> Path:
        workspace = run / "workspace"
        workspace.mkdir()
        if content is not None:
            (workspace / "task.prompt").write_text(content, encoding="utf-8")
        return workspace

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(
        supervisor.container_run, "prepare_workspace", prepare_workspace
    )
    monkeypatch.setattr(
        supervisor.ollama_model,
        "prepare_model",
        lambda model, context: pytest.fail("Ollama must not be contacted"),
    )
    monkeypatch.setattr(sys, "argv", ["supervisor.py"])
    assert supervisor.main() == 1


def test_failed_network_verification_stops_before_agent_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailedGuard:
        def __init__(self, name: str, token: str, digest: str, mode: str) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("Network boundary could not be verified")

    def prepare_workspace(source: Path, run: Path) -> Path:
        workspace = run / "workspace"
        workspace.mkdir()
        (workspace / "task.prompt").write_text("task", encoding="utf-8")
        return workspace

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(
        supervisor.container_run, "prepare_workspace", prepare_workspace
    )
    monkeypatch.setattr(
        supervisor.ollama_model,
        "prepare_model",
        lambda model, context: {"model_digest": "digest"},
    )
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", FailedGuard)
    monkeypatch.setattr(
        supervisor, "supervise", lambda *args: pytest.fail("Agent must not start")
    )
    monkeypatch.setattr(sys, "argv", ["supervisor.py"])
    assert supervisor.main() == 1


def test_event_log_omits_streaming_fragments(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "complete", 3)
    assert result["status"] == "settled"
    types = [record.get("type") for record in records]
    assert "message_update" not in types
    assert "tool_execution_update" not in types
    assert "message_end" in types
    assert "agent_settled" in types


def test_repeated_failed_calls_stop_run_and_preserve_evidence(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "loop", 5)
    assert result["status"] == "loop_detected"
    assert result["termination"] == "graceful"
    assert result["loop_detection"]["failure_count"] == 10
    assert result["loop_detection"]["tool_name"] == "bash"
    assert sum(r.get("type") == "tool_execution_start" for r in records) == 10
    assert sum(r.get("type") == "tool_execution_end" for r in records) == 10
    assert any(r.get("command") == "abort" and r.get("success") for r in records)


def test_loop_detector_counts_in_start_order_with_parallel_results() -> None:
    detector = supervisor.LoopDetector()
    for i in range(10):
        detector.observe(
            {
                "type": "tool_execution_start",
                "toolCallId": str(i),
                "toolName": "bash",
                "args": {"command": "bad"},
            }
        )
    for i in range(9, 0, -1):
        assert not detector.observe(
            {"type": "tool_execution_end", "toolCallId": str(i), "isError": True}
        )
    assert detector.observe(
        {"type": "tool_execution_end", "toolCallId": "0", "isError": True}
    )


def test_loop_abort_forces_unresponsive_agent_to_stop(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "loop_hang", 5)
    assert result["status"] == "loop_detected"
    assert result["termination"] == "forced"
    assert sum(r.get("type") == "tool_execution_end" for r in records) == 10


def test_loop_detector_finds_completed_streak_after_unfinished_call() -> None:
    detector = supervisor.LoopDetector()
    detector.observe(
        {
            "type": "tool_execution_start",
            "toolCallId": "stalled",
            "toolName": "read",
            "args": {"path": "x"},
        }
    )
    for i in range(10):
        detector.observe(
            {
                "type": "tool_execution_start",
                "toolCallId": str(i),
                "toolName": "bash",
                "args": {"command": "bad"},
            }
        )
    for i in range(9):
        assert not detector.observe(
            {"type": "tool_execution_end", "toolCallId": str(i), "isError": True}
        )
    assert detector.observe(
        {"type": "tool_execution_end", "toolCallId": "9", "isError": True}
    )


@pytest.mark.parametrize(
    ("tool", "args", "error"),
    [
        ("read", {"command": "bad"}, True),
        ("bash", {"command": "different"}, True),
        ("bash", {"command": "bad"}, False),
        ("bash", {"command": "bad"}, None),
    ],
)
def test_each_condition_independently_resets_streak(
    tool: str, args: dict, error: bool | None
) -> None:
    detector = supervisor.LoopDetector()

    def call(call_id: str, name: str, arguments: dict, is_error: bool | None) -> bool:
        detector.observe(
            {
                "type": "tool_execution_start",
                "toolCallId": call_id,
                "toolName": name,
                "args": arguments,
            }
        )
        end = {"type": "tool_execution_end", "toolCallId": call_id}
        if is_error is not None:
            end["isError"] = is_error
        return detector.observe(end)

    for i in range(9):
        assert not call(f"before-{i}", "bash", {"command": "bad"}, True)
    assert not call("reset", tool, args, error)
    for i in range(9):
        assert not call(f"after-{i}", "bash", {"command": "bad"}, True)
    assert call("trigger", "bash", {"command": "bad"}, True)
