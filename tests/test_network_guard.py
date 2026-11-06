import io
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import network_guard
from sokoban_authority import SokobanAuthority


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
