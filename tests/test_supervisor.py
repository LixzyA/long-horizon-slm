import ctypes
import json
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
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


def test_startup_failure_is_not_reported_as_completion(tmp_path: Path) -> None:
    result, _ = run_case(tmp_path, "exit", 3)
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
