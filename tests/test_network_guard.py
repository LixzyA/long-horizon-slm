import io
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import network_guard
from sokoban_authority import SokobanAuthority


@pytest.mark.parametrize("result", ["sha256:" + "a" * 64, "", "mutable-tag"])
def test_image_resolution_requires_an_immutable_id(monkeypatch: pytest.MonkeyPatch, result: str) -> None:
    def inspect(arguments, timeout=30):
        assert arguments == ["image", "inspect", "--format", "{{.Id}}", "image:tag"]
        return subprocess.CompletedProcess(arguments, 0, result + "\n", "")

    monkeypatch.setattr(network_guard, "run_docker", inspect)
    if result.startswith("sha256:"):
        assert network_guard.resolve_image("image:tag") == result
    else:
        with pytest.raises(RuntimeError, match="image ID"):
            network_guard.resolve_image("image:tag")


def test_only_ipv4_isolated_internal_network_is_accepted() -> None:
    good = {
        "Internal": True,
        "EnableIPv6": False,
        "Options": {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"},
    }
    assert network_guard.verify_network_settings(good)
    assert not network_guard.verify_network_settings({**good, "Internal": False})
    assert not network_guard.verify_network_settings({**good, "EnableIPv6": True})
    assert not network_guard.verify_network_settings({**good, "Options": {}})


def test_gateway_and_probe_use_the_pinned_image(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = []
    image = "sha256:" + "a" * 64
    process = SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None, wait=lambda **_: 0)

    def run(arguments, timeout=30):
        commands.append(arguments)
        if arguments[:2] == ["network", "inspect"]:
            output = json.dumps([{
                "Internal": True, "EnableIPv6": False,
                "Options": {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"},
            }])
        else:
            output = "verified" if arguments[0] == "run" else "127.0.0.1"
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(network_guard, "run_docker", run)
    monkeypatch.setattr(network_guard.subprocess, "Popen", lambda command, **_: commands.append(command) or process)
    monkeypatch.setattr(network_guard.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "true", ""))
    guard = network_guard.GatewaySession("test", "token", "digest", image=image)
    try:
        guard.start()
        launches = [c for c in commands if c[:2] == ["docker", "run"] or c[0] == "run"]
        assert len(launches) == 2
        assert all(image in c and network_guard.IMAGE not in c for c in launches)
    finally:
        assert guard.close()


def test_game_requests_cross_gateway_stdio_and_update_authority(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    request = {"type": "game_request", "id": "abc", "action": "up"}
    process = type("Process", (), {})()
    process.stdout = io.BytesIO((json.dumps(request) + "\n").encode())
    process.stdin = io.BytesIO()
    closing = threading.Event()
    closing.set()
    network_guard.serve_game_requests(process, game, closing)
    reply = json.loads(process.stdin.getvalue())
    assert reply["id"] == "abc" and reply["ok"]
    assert "Remaining: 23" in reply["output"]
    assert json.loads(game.path.read_text(encoding="utf-8"))["actions"][0]["action"] == "up"


def test_gateway_exit_or_bad_request_marks_game_failed(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    process = type("Process", (), {})()
    process.stdout = io.BytesIO(b"not json\n")
    process.stdin = io.BytesIO()
    network_guard.serve_game_requests(process, game, threading.Event())
    assert game.failed.is_set()
    assert "Actions: 0 / 24" in game.execute("show")
