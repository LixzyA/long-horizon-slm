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



class FakeBackend:
    def __init__(self, executable, model, run_dir):
        self.model = Path("C:/model.gguf")
        self.token = "private-backend-key"
        self.closed = False
        self.info = {"backend": "llama.cpp", "model": "Qwen3.5-custom-32k", "allocated_context": 32768,
                     "llamacpp_version": "b12110", "model_sha256": "verified-hash"}

    def start(self):
        return self.info

    def check_alive(self):
        if self.closed:
            raise RuntimeError("backend stopped")

    def close(self):
        self.closed = True
        return True


@pytest.fixture(autouse=True)
def backend_stub(monkeypatch):
    monkeypatch.setattr(supervisor.llamacpp_model, "LlamaServer", FakeBackend)


BACKEND_ARGS = ["--llama-server", "server.exe", "--model-file", "model.gguf"]


def test_backend_paths_use_local_config_and_allow_overrides(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("llama_server = 'server.exe'\nmodel_file = 'model.gguf'\n", encoding="utf-8")
    assert supervisor.backend_paths(config, None, None) == (Path("server.exe"), Path("model.gguf"))
    assert supervisor.backend_paths(config, Path("other.exe"), None) == (Path("other.exe"), Path("model.gguf"))
    config.write_text("invalid = [", encoding="utf-8")
    assert supervisor.backend_paths(config, Path("a"), Path("b")) == (Path("a"), Path("b"))
    with pytest.raises(ValueError, match="Cannot read"):
        supervisor.backend_paths(config, None, None)
    config.unlink()
    with pytest.raises(ValueError, match="llama_server"):
        supervisor.backend_paths(config, None, None)


def test_example_config_is_valid_and_reports_unset_paths() -> None:
    config = ROOT / "config.example.toml"
    with pytest.raises(ValueError, match="Set llama_server"):
        supervisor.backend_paths(config, None, None)
    with pytest.raises(ValueError, match="Set model_file"):
        supervisor.backend_paths(config, Path("server.exe"), None)


def test_supervisor_accepts_paths_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.toml").write_text("llama_server = 'local.exe'\nmodel_file = 'local.gguf'\n", encoding="utf-8")
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["supervisor.py"])
    def stop_after_parsing(source, run, **kwargs):
        raise ValueError("configuration parsed")
    monkeypatch.setattr(supervisor.container_run, "prepare_workspace", stop_after_parsing)
    assert supervisor.main() == 1
    outcome = next((tmp_path / "supervisor-runs").glob("*/*/outcome.json"))
    assert json.loads(outcome.read_text(encoding="utf-8"))["error"] == "configuration parsed"

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


def test_starts_agent_in_project_directory(tmp_path: Path) -> None:
    result, records = run_case(tmp_path, "complete", 3)
    assert result["status"] == "settled"
    cwd = next(r["cwd"] for r in records if r.get("type") == "test_cwd")
    assert Path(cwd) == ROOT


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


@pytest.mark.parametrize("phase", ["startup", "runtime", "settled"])
def test_owned_backend_exit_stops_supervision(tmp_path: Path, phase: str) -> None:
    class Backend:
        def check_alive(self):
            events = tmp_path / "events.jsonl"
            marker = '"agent_settled"' if phase == "settled" else '"supervisor-prompt"'
            if phase == "startup" or (events.exists() and marker in events.read_text(encoding="utf-8")):
                raise RuntimeError("llama.cpp exited unexpectedly")

    result = supervise([sys.executable, str(FAKE), "complete" if phase == "settled" else "abort"], "test", 3, tmp_path, backend=Backend())
    assert result["status"] == ("startup_error" if phase == "startup" else "run_error")
    assert "llama.cpp exited" in result["error"]
    assert (result["prompt_submitted_at_utc"] is None) == (phase == "startup")
    assert result["launcher_exit_code"] is not None
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8")) == result


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
@pytest.mark.parametrize("failed_cleanup", [None, "container_cleanup", "backend_cleanup", "gateway_cleanup"])
def test_launcher_uses_isolated_container_and_model_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_cleanup: str | None,
    thinking: str,
    pinned_image: str,
) -> None:
    seen = []
    prompts = []

    class Guard:
        def __init__(self, name: str, token: str, model_path: str, mode: str, *, backend_token: str, image: str, game=None, backend_kind="llamacpp") -> None:
            assert mode == thinking
            assert backend_token == "private-backend-key"
            assert image == pinned_image
            self.network = "verified-network"

        def start(self) -> None:
            pass

        def close(self) -> bool:
            return failed_cleanup != "gateway_cleanup"

    def fake_supervise(
        command: list[str], prompt: str, limit_seconds: float, run_dir: Path, **kwargs
    ) -> dict:
        assert (run_dir / "workspace" / "output").is_dir()
        assert run_dir.parent.name == "local"
        seen.extend(command)
        prompts.append(prompt)
        return {"status": "settled"}

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "supervise", fake_supervise)

    def prepare_workspace(source: Path, run: Path, **kwargs: object) -> Path:
        workspace = run / "workspace"
        workspace.mkdir()
        (workspace / "task.prompt").write_text(
            "Assignment content: solve Sokoban.", encoding="utf-8"
        )
        (workspace / "src").mkdir()
        (workspace / "src" / "sokoban.py").write_bytes(GAME_PATH.read_bytes())
        return workspace

    monkeypatch.setattr(
        supervisor.container_run, "prepare_workspace", prepare_workspace
    )
    monkeypatch.setattr(
        supervisor.llamacpp_model.LlamaServer,
        "start",
        lambda self: self.info,
    )
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(FakeBackend, "close", lambda self: failed_cleanup != "backend_cleanup")
    monkeypatch.setattr(
        supervisor.container_run, "cleanup_container", lambda name: failed_cleanup != "container_cleanup"
    )
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--thinking", thinking] + BACKEND_ARGS)
    assert supervisor.main() == (1 if failed_cleanup else 0)
    if failed_cleanup:
        outcomes = list((tmp_path / "supervisor-runs").glob("*/*/outcome.json"))
        assert (
            json.loads(outcomes[0].read_text(encoding="utf-8"))[failed_cleanup]
            == "failed"
        )
    assert seen[:2] == ["docker", "run"]
    assert seen[-1] == pinned_image
    assert "verified-network" in seen
    assert f"THINKING_MODE={thinking}" in seen
    assert not any("PI_REPETITION" in value for value in seen)
    model_info = list((tmp_path / "supervisor-runs").glob("*/*/model.json"))
    recorded = json.loads(model_info[0].read_text(encoding="utf-8"))
    assert recorded["container_image_id"] == pinned_image
    assert recorded["llamacpp_version"] == "b12110"
    assert "private-backend-key" not in json.dumps(recorded)
    assert not any("BACKEND_TOKEN=" in argument for argument in seen)
    assert (
        json.loads(model_info[0].read_text(encoding="utf-8"))["model"] == "Qwen3.5-custom-32k"
    )
    assert json.loads(model_info[0].read_text(encoding="utf-8"))["thinking"] is (
        thinking == "high"
    )
    assert "Assignment content: solve Sokoban." in prompts[0]
    assert "Read task.prompt" not in prompts[0]


@pytest.mark.parametrize("content", [None, "   "])
def test_missing_or_empty_assignment_stops_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None
) -> None:
    def prepare_workspace(source: Path, run: Path, **kwargs: object) -> Path:
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
        supervisor.llamacpp_model.LlamaServer,
        "start",
        lambda self: pytest.fail("Backend must not start"),
    )
    monkeypatch.setattr(sys, "argv", ["supervisor.py"] + BACKEND_ARGS)
    assert supervisor.main() == 1


def test_failed_network_verification_stops_before_agent_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str,
) -> None:
    class FailedGuard:
        def __init__(self, name: str, token: str, model_path: str, mode: str, *, backend_token: str, image: str, game=None, backend_kind="llamacpp") -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("Network boundary could not be verified")

        def close(self) -> bool:
            return True

    def prepare_workspace(source: Path, run: Path, **kwargs: object) -> Path:
        workspace = run / "workspace"
        workspace.mkdir()
        (workspace / "task.prompt").write_text("task", encoding="utf-8")
        (workspace / "src").mkdir()
        (workspace / "src" / "sokoban.py").write_bytes(GAME_PATH.read_bytes())
        return workspace

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(
        supervisor.container_run, "prepare_workspace", prepare_workspace
    )
    monkeypatch.setattr(
        supervisor.llamacpp_model.LlamaServer,
        "start",
        lambda self: self.info,
    )
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", FailedGuard)
    monkeypatch.setattr(
        supervisor, "supervise", lambda *args: pytest.fail("Agent must not start")
    )
    monkeypatch.setattr(sys, "argv", ["supervisor.py"] + BACKEND_ARGS)
    assert supervisor.main() == 1


@pytest.mark.parametrize("phase", ["backend_startup", "gateway_startup", "execution"])
def test_interrupt_cleans_up_owned_backend_and_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str, phase: str,
) -> None:
    closed = []

    class Backend(FakeBackend):
        def start(self):
            if phase == "backend_startup":
                raise KeyboardInterrupt
            return self.info

        def close(self):
            closed.append("backend")
            return True

    class Guard:
        def __init__(self, *args, **kwargs):
            self.network = "network"

        def start(self):
            if phase == "gateway_startup":
                raise KeyboardInterrupt

        def close(self):
            closed.append("gateway")
            return True

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    import shutil
    shutil.copytree(ROOT / "sokoban_workspace", tmp_path / "sokoban_workspace")
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.llamacpp_model, "LlamaServer", Backend)
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor, "supervise", interrupt)
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda name: closed.append("agent") or True)
    monkeypatch.setattr(sys, "argv", ["supervisor.py"] + BACKEND_ARGS)
    assert supervisor.main() == 1
    result = json.loads(next((tmp_path / "supervisor-runs").glob("*/*/outcome.json")).read_text(encoding="utf-8"))
    assert result["status"] == "interrupted"
    expected = {"backend"}
    if phase != "backend_startup":
        expected.add("gateway")
    if phase == "execution":
        expected.add("agent")
    assert set(closed) == expected


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


@pytest.mark.parametrize("task_flag", [[], ["--task", "sokoban"]])
def test_task_selects_sokoban_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_flag: list[str]
) -> None:
    def prepare_workspace(source: Path, run: Path, **kwargs: object) -> Path:
        assert source == tmp_path / "sokoban_workspace"
        raise ValueError("stop before launch")

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.container_run, "prepare_workspace", prepare_workspace)
    monkeypatch.setattr(sys, "argv", ["supervisor.py"] + task_flag + BACKEND_ARGS)
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
        workspace = next((tmp_path / "supervisor-runs").glob("*/*/workspace"))
        assert (workspace / "output").is_dir()
        assert list((workspace / "output").iterdir()) == []
        assert not (workspace / "AGENTS.md").exists()
        assert not (workspace / "src" / "sokoban.py").exists()
        assert (source / "src" / "sokoban.py").read_bytes() == original_rules
        assert (workspace.parent / "sokoban_rules.py").read_bytes() == original_rules
        model_started.append(True)
        raise RuntimeError("stop before launch")

    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.llamacpp_model.LlamaServer, "start", prepare_model)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", "sokoban"] + BACKEND_ARGS)
    assert supervisor.main() == 1
    assert bool(model_started) is not existing_output
    workspace = next((tmp_path / "supervisor-runs").glob("*/*/workspace"))
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
    monkeypatch.setattr("sokoban_authority.load_puzzle", lambda _: {
        "id": "baseline", "board": ["#######", "#.    #", "#  @  #", "#  $  #", "#     #", "#     #", "#######"], "action_limit": 24,
    })
    seen = {}

    class Guard:
        def __init__(self, name: str, token: str, model_path: str, mode: str, game: SokobanAuthority, *, backend_token: str, image: str, backend_kind="llamacpp") -> None:
            assert image == pinned_image
            self.network = "network"
            seen["game"] = game

        def start(self) -> None:
            pass

        def close(self) -> bool:
            return True

    def fake_supervise(command, prompt, limit_seconds, run_dir, *, game, stop_at_limit, backend):
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
    monkeypatch.setattr(supervisor.llamacpp_model.LlamaServer, "start", lambda self: self.info)
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda _: True)
    monkeypatch.setattr(supervisor, "supervise", fake_supervise)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", "sokoban"] + BACKEND_ARGS)
    assert supervisor.main() == 1
    record = next((tmp_path / "supervisor-runs").glob("*/*/game.json"))
    assert len(json.loads(record.read_text(encoding="utf-8"))["actions"]) == 24


@pytest.mark.parametrize("variant", ["standard", "concise"])
@pytest.mark.parametrize("task_flag", [[], ["--task", "sokoban"]])
def test_selected_puzzle_prompt_and_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str, variant: str, task_flag: list[str]) -> None:
    import shutil
    source = tmp_path / "sokoban_workspace"
    shutil.copytree(ROOT / "sokoban_workspace", source)
    prompt_file = ROOT / "src" / "sokoban" / "concise.prompt"
    if variant == "concise":
        target = tmp_path / "src" / "sokoban"
        target.mkdir(parents=True)
        shutil.copy(prompt_file, target / "concise.prompt")
    template = (source / "task.prompt").read_text(encoding="utf-8") if variant == "standard" else prompt_file.read_text(encoding="utf-8")
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)

    class Guard:
        def __init__(self, *args, **kwargs):
            self.network = "network"
        def start(self):
            pass
        def close(self):
            return True

    def fake_supervise(command, prompt, limit_seconds, run_dir, *, game, **kwargs):
        assert prompt == supervisor.PROMPT + template.replace("{ACTION_LIMIT}", "8")
        assert json.loads((run_dir / "model.json").read_text(encoding="utf-8"))["sokoban_prompt"] == variant
        assert "You have 8 actions" in prompt
        assert "action 8" in prompt and "{ACTION_LIMIT}" not in prompt
        assert "You have 8 actions" in (run_dir / "workspace" / "task.prompt").read_text(encoding="utf-8")
        assert "Remaining: 8" in game.execute("show")
        assert json.loads((run_dir / "puzzle.json").read_text())["id"] == "one-push"
        assert not (run_dir / "workspace" / "puzzle.json").exists()
        return {"status": "settled"}

    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor, "supervise", fake_supervise)
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda _: True)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--puzzle", "one-push", "--sokoban-prompt", variant] + task_flag + BACKEND_ARGS)
    assert supervisor.main() == 0


def test_concise_prompt_changes_only_action_instructions() -> None:
    standard = (ROOT / "sokoban_workspace" / "task.prompt").read_text(encoding="utf-8")
    concise = (ROOT / "src" / "sokoban" / "concise.prompt").read_text(encoding="utf-8")
    header = "## Output requirements for each action\n\n"
    ending = "\n\nIf the game is solved before action {ACTION_LIMIT},"
    assert standard.split(header)[0] == concise.split(header)[0]
    assert standard.split(ending)[1] == concise.split(ending)[1]
    assert "Briefly check the current positions" in concise
    assert "Do not repeat the full board" in concise
    assert "Put your detailed reasoning" not in concise


def test_invalid_sokoban_prompt_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--sokoban-prompt", "unknown"] + BACKEND_ARGS)
    with pytest.raises(SystemExit) as error:
        supervisor.main()
    assert error.value.code == 2


@pytest.mark.parametrize("content", [None, "   "])
def test_missing_or_empty_concise_prompt_stops_before_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None
) -> None:
    def prepare_workspace(source: Path, run: Path, **kwargs: object) -> Path:
        workspace = run / "workspace"
        workspace.mkdir()
        return workspace

    if content is not None:
        path = tmp_path / "src" / "sokoban" / "concise.prompt"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor.container_run, "prepare_workspace", prepare_workspace)
    monkeypatch.setattr(supervisor.llamacpp_model.LlamaServer, "start", lambda self: pytest.fail("Backend must not start"))
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", "sokoban", "--sokoban-prompt", "concise"] + BACKEND_ARGS)
    assert supervisor.main() == 1


def test_openrouter_launcher_keeps_key_out_of_agent_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str,
) -> None:
    import shutil
    shutil.copytree(ROOT / "sokoban_workspace", tmp_path / "sokoban_workspace")
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-key")
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--backend", "openrouter"])
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda _: True)

    class Guard:
        def __init__(self, *args, **kwargs):
            assert kwargs["backend_kind"] == "openrouter"
            assert kwargs["backend_token"] == ""
            self.network = "network"
        def start(self):
            pass
        def close(self):
            return True

    def run(command, prompt, limit_seconds, run_dir, *, game, stop_at_limit, backend):
        assert run_dir.parent.name == "deepseek"
        assert "private-key" not in str(command)
        assert "OPENROUTER_API_KEY" not in str(command)
        assert backend is None
        assert stop_at_limit()
        return {"status": "action_limit"}

    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor, "supervise", run)
    assert supervisor.main() == 1
    metadata = json.loads(next((tmp_path / "supervisor-runs").glob("*/*/model.json")).read_text(encoding="utf-8"))
    assert metadata["backend"] == "OpenRouter"
    assert metadata["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert "private-key" not in str(metadata)


def test_huggingface_token_reads_dotenv_and_prefers_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    file = tmp_path / ".env"
    file.write_text("OTHER_KEY=ignored\nHF_TOKEN=\"file-token\" # comment\n", encoding="utf-8")
    assert supervisor.huggingface_token(file) == "file-token"
    monkeypatch.setenv("HF_TOKEN", "environment-token")
    assert supervisor.huggingface_token(file) == "environment-token"
    monkeypatch.delenv("HF_TOKEN")
    file.write_text("HF_TOKEN=one\nHF_TOKEN=two\n", encoding="utf-8")
    with pytest.raises(ValueError, match="HF_TOKEN"):
        supervisor.huggingface_token(file)
    file.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="Cannot read .env"):
        supervisor.huggingface_token(file)


def test_huggingface_launcher_uses_dotenv_without_exposing_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_image: str) -> None:
    import shutil
    shutil.copytree(ROOT / "sokoban_workspace", tmp_path / "sokoban_workspace")
    (tmp_path / ".env").write_text("HF_TOKEN=private-key\n", encoding="utf-8")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--backend", "huggingface"])
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda _: True)
    class Guard:
        def __init__(self, *args, **kwargs):
            assert kwargs["backend_kind"] == "huggingface"
            self.network = "network"
        def start(self): pass
        def close(self): return True
    def run(command, prompt, limit_seconds, run_dir, *, game, stop_at_limit, backend):
        assert run_dir.parent.name == "deepseek-huggingface"
        assert "private-key" not in str(command) and "HF_TOKEN" not in str(command)
        assert backend is None and stop_at_limit()
        return {"status": "action_limit"}
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor, "supervise", run)
    assert supervisor.main() == 1
    metadata = json.loads(next((tmp_path / "supervisor-runs" / "deepseek-huggingface").glob("*/model.json")).read_text(encoding="utf-8"))
    assert metadata["backend"] == "Hugging Face"
    assert metadata["model"] == "deepseek-ai/DeepSeek-V4.1-Flash"
    assert "private-key" not in json.dumps(metadata)
