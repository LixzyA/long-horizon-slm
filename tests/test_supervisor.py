import ctypes
import json
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import supervisor
from sokoban_authority import GAME_PATH, SokobanAuthority
from supervisor import supervise

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("fake_pi.py")


@pytest.fixture
def pinned_image(monkeypatch: pytest.MonkeyPatch) -> str:
    image_id = "sha256:" + "a" * 64
    monkeypatch.setattr(supervisor.network_guard, "resolve_image", lambda _: image_id)
    return image_id


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


@pytest.mark.parametrize("recovered", [False, True])
def test_model_error_is_recorded_unless_a_retry_recovers(tmp_path: Path, recovered: bool) -> None:
    mode = "model_error_recovered" if recovered else "model_error"
    result, records = run_case(tmp_path, mode, 3)
    saved = json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))
    assert saved == result
    assert any(r.get("message", {}).get("stopReason") == "error" for r in records)
    assert result["status"] == ("settled" if recovered else "run_error")
    assert result["model_stop_reason"] == ("stop" if recovered else "error")
    if recovered:
        assert "error" not in result
    else:
        assert result["error"] == "503 model unavailable"


def test_timeout_requests_abort_before_forced_termination(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "abort")
    assert result["status"] == "timeout"
    assert result["termination"] == "graceful"
    assert any(r.get("command") == "abort" and r.get("success") for r in records)


@pytest.mark.parametrize(
    ("actions", "outcome"),
    [
        (["undo"] * 24, "action_limit_reached"),
        (["undo"] * 18 + ["left", "down", "down", "right", "up", "up"], "solved"),
    ],
)
def test_game_action_limit_aborts_agent_and_keeps_authoritative_result(
    tmp_path: Path, actions: list[str], outcome: str
) -> None:
    game = SokobanAuthority(tmp_path)
    stopped = []

    def play_after_prompt() -> None:
        deadline = time.monotonic() + 8
        events = tmp_path / "events.jsonl"
        while time.monotonic() < deadline:
            if events.exists() and '"supervisor-prompt"' in events.read_text(encoding="utf-8"):
                for action in actions:
                    game.execute(action)
                return
            time.sleep(0.02)

    player = threading.Thread(target=play_after_prompt, daemon=True)
    player.start()
    result = supervise(
        [sys.executable, str(FAKE), "abort"], "test task", 10, tmp_path,
        grace_seconds=0.5, game=game, stop_at_limit=lambda: stopped.append(True) or True,
    )
    player.join(timeout=2)
    assert result["status"] == "action_limit"
    assert result["termination"] == "forced"
    assert stopped == [True]
    assert result["game"] == {"outcome": outcome, "actions": 24, "limit": 24}
    assert len(json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))["actions"]) == 24


def test_game_service_failure_stops_run(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    game.failed.set()
    result = supervise(
        [sys.executable, str(FAKE), "hang"], "test task", 10, tmp_path,
        grace_seconds=0.5, game=game,
    )
    assert result["status"] == "run_error"
    assert "game service" in result["error"].lower()


@pytest.mark.parametrize("mode", ["complete", "abort", "crash"])
def test_game_cannot_change_after_supervisor_finishes(tmp_path: Path, mode: str) -> None:
    game = SokobanAuthority(tmp_path)
    for _ in range(23):
        game.execute("undo")
    result = supervise(
        [sys.executable, str(FAKE), mode], "test task", 0.35, tmp_path,
        grace_seconds=0.5, game=game,
    )
    saved = game.path.read_bytes()
    game.execute("undo")
    assert game.path.read_bytes() == saved
    recorded = json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))
    assert recorded["game"] == result["game"] == game.summary()
    assert not game.limit_reached.is_set()


@pytest.mark.parametrize("mode", ["complete", "abort", "crash"])
def test_final_action_in_flight_takes_precedence_at_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    game = SokobanAuthority(tmp_path)
    for _ in range(23):
        game.execute("undo")
    writing = threading.Event()
    release = threading.Event()
    replace = supervisor.os.replace

    def delayed_replace(source, destination):
        writing.set()
        assert release.wait(timeout=8)
        replace(source, destination)

    monkeypatch.setattr("sokoban_authority.os.replace", delayed_replace)
    player = threading.Thread(target=game.execute, args=("undo",))
    player.start()
    assert writing.wait(timeout=3)
    close = game.close

    def close_after_pending_action() -> None:
        release.set()
        close()

    monkeypatch.setattr(game, "close", close_after_pending_action)
    stopped = []
    try:
        result = supervise(
            [sys.executable, str(FAKE), mode], "test task", 0.35, tmp_path,
            grace_seconds=0.5, game=game, stop_at_limit=lambda: stopped.append(True) or True,
        )
    finally:
        release.set()
        player.join(timeout=3)
    assert result["status"] == "action_limit"
    assert result["termination"] == "forced"
    assert stopped == [True]
    assert result["game"] == {"outcome": "action_limit_reached", "actions": 24, "limit": 24}
    assert len(json.loads(game.path.read_text(encoding="utf-8"))["actions"]) == 24


def test_save_failure_during_shutdown_is_not_reported_as_settled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = SokobanAuthority(tmp_path)
    writing = threading.Event()
    release = threading.Event()

    def failed_replace(*args):
        writing.set()
        assert release.wait(timeout=8)
        raise OSError("disk error")

    def pending_action() -> None:
        with pytest.raises(OSError, match="disk error"):
            game.execute("undo")

    monkeypatch.setattr("sokoban_authority.os.replace", failed_replace)
    player = threading.Thread(target=pending_action)
    player.start()
    assert writing.wait(timeout=3)
    close = game.close

    def close_after_pending_action() -> None:
        release.set()
        close()

    monkeypatch.setattr(game, "close", close_after_pending_action)
    try:
        result = supervise(
            [sys.executable, str(FAKE), "complete"], "test task", 3, tmp_path,
            grace_seconds=0.5, game=game,
        )
    finally:
        release.set()
        player.join(timeout=3)
    assert result["status"] == "run_error"
    assert result["termination"] == "forced"
    assert "game service" in result["error"].lower()
    assert game.failed.is_set()
    assert result["game"]["actions"] == 0


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


@pytest.mark.parametrize("phase", ["startup", "runtime"])
@pytest.mark.parametrize("value", [[], None, 7, "unexpected"])
def test_non_object_rpc_is_reported_without_crashing(tmp_path: Path, phase: str, value: object) -> None:
    result = supervise(
        [sys.executable, str(FAKE), "invalid_" + phase, json.dumps(value)],
        "test task", 3, tmp_path, grace_seconds=0.5,
    )
    saved = json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))
    assert saved == result
    assert result["status"] == ("startup_error" if phase == "startup" else "run_error")
    assert (result["prompt_submitted_at_utc"] is None) == (phase == "startup")
    assert "non-object JSON" in result["error"]


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
    pinned_image: str,
) -> None:
    seen = []
    prompts = []

    class Guard:
        def __init__(self, name: str, token: str, digest: str, mode: str, *, image: str) -> None:
            assert mode == thinking
            assert image == pinned_image
            self.network = "verified-network"

        def start(self) -> None:
            pass

        def close(self) -> bool:
            return True

    def fake_supervise(
        command: list[str], prompt: str, limit_seconds: float, run_dir: Path
    ) -> dict:
        assert not (run_dir / "workspace" / "output").exists()
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
            "allocated_context": 32768,
            "ollama_version": "0.40.13",
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
    assert seen[-1] == pinned_image
    assert "verified-network" in seen
    assert f"THINKING_MODE={thinking}" in seen
    assert not any("PI_REPETITION" in value for value in seen)
    model_info = list((tmp_path / "supervisor-runs").glob("*/model.json"))
    recorded = json.loads(model_info[0].read_text(encoding="utf-8"))
    assert recorded["container_image_id"] == pinned_image
    assert recorded["ollama_version"] == "0.40.13"
    assert (
        json.loads(model_info[0].read_text(encoding="utf-8"))["model"] == "Qwen3.5-custom-32k"
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str,
) -> None:
    class FailedGuard:
        def __init__(self, name: str, token: str, digest: str, mode: str, *, image: str) -> None:
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


@pytest.mark.parametrize(
    ("task", "expected"),
    [("profile", "experiment_workspace"), ("sokoban", "sokoban_workspace")],
)
def test_task_selects_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task: str, expected: str
) -> None:
    def prepare_workspace(source: Path, run: Path, **kwargs: object) -> Path:
        assert source.name == expected
        raise ValueError("stop before launch")

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.container_run, "prepare_workspace", prepare_workspace)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", task])
    assert supervisor.main() == 1


@pytest.mark.parametrize("existing_output", [False, True])
def test_sokoban_output_is_created_before_model_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_output: bool
) -> None:
    source = tmp_path / "sokoban_workspace"
    source.mkdir()
    (source / "task.prompt").write_text("Sokoban task", encoding="utf-8")
    (source / "src").mkdir()
    original_rules = GAME_PATH.read_bytes()
    (source / "src" / "sokoban.py").write_bytes(original_rules)
    if existing_output:
        (source / "output").mkdir()
        (source / "output" / "existing.txt").write_text("keep", encoding="utf-8")
    model_started = []

    def prepare_model(*args: object) -> dict:
        workspace = next((tmp_path / "supervisor-runs").glob("*/workspace"))
        assert (workspace / "output").is_dir()
        assert list((workspace / "output").iterdir()) == []
        assert not (workspace / "AGENTS.md").exists()
        assert not (workspace / "src" / "sokoban.py").exists()
        assert (source / "src" / "sokoban.py").read_bytes() == original_rules
        assert (workspace.parent / "sokoban_rules.py").read_bytes() == original_rules
        model_started.append(True)
        raise RuntimeError("stop before launch")

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.ollama_model, "prepare_model", prepare_model)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", "sokoban"])
    assert supervisor.main() == 1
    assert bool(model_started) is not existing_output
    workspace = next((tmp_path / "supervisor-runs").glob("*/workspace"))
    if existing_output:
        assert (source / "output" / "existing.txt").read_text(encoding="utf-8") == "keep"
        assert (workspace / "output" / "existing.txt").read_text(encoding="utf-8") == "keep"
    else:
        assert not (source / "output").exists()


def test_sokoban_launcher_uses_same_authority_for_gateway_and_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str,
) -> None:
    source = tmp_path / "sokoban_workspace"
    source.mkdir()
    (source / "task.prompt").write_text("Sokoban task", encoding="utf-8")
    (source / "src").mkdir()
    copied_rules = GAME_PATH.read_text(encoding="utf-8").replace('"#  .  #",', '"#.    #",')
    (source / "src" / "sokoban.py").write_text(copied_rules, encoding="utf-8")
    seen = {}

    class Guard:
        def __init__(self, name: str, token: str, digest: str, mode: str, game: SokobanAuthority, *, image: str) -> None:
            assert image == pinned_image
            self.network = "network"
            seen["game"] = game

        def start(self) -> None:
            pass

        def close(self) -> bool:
            return True

    def fake_supervise(command, prompt, limit_seconds, run_dir, *, game, stop_at_limit):
        assert command[-1] == pinned_image
        assert game is seen["game"]
        assert game.path == run_dir / "game.json"
        assert "Goal: row 1, column 1" in game.execute("show")
        assert (run_dir / "sokoban_rules.py").read_text(encoding="utf-8") == copied_rules
        assert (run_dir / "workspace" / "output").is_dir()
        for _ in range(24):
            game.execute("undo")
        assert stop_at_limit()
        return {"status": "action_limit"}

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.ollama_model, "prepare_model", lambda *_: {"model_digest": "digest"})
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda _: True)
    monkeypatch.setattr(supervisor, "supervise", fake_supervise)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", "sokoban"])
    assert supervisor.main() == 1
    record = next((tmp_path / "supervisor-runs").glob("*/game.json"))
    assert len(json.loads(record.read_text(encoding="utf-8"))["actions"]) == 24
