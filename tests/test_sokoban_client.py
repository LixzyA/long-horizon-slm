import http.client
import importlib.util
import json
import os
import queue
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sokoban_authority import SokobanAuthority
import network_guard


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_game_client_receives_authoritative_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    game = SokobanAuthority(tmp_path)
    gateway = load_module("test_game_gateway", ROOT / "docker" / "gateway.py")
    client = load_module("test_game_client", ROOT / "sokoban_workspace" / "src" / "play.py")
    monkeypatch.setenv("GATEWAY_TOKEN", "token")
    monkeypatch.setenv("MODEL_PROXY_TOKEN", "token")
    monkeypatch.setenv("SOKOBAN_ENABLED", "1")
    monkeypatch.setattr(gateway, "request_game", game.execute)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.ModelHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original = http.client.HTTPConnection
    monkeypatch.setattr(
        client.http.client, "HTTPConnection",
        lambda host, port, timeout: original("127.0.0.1", server.server_port, timeout=timeout),
    )
    try:
        monkeypatch.setattr(sys, "argv", ["play.py", "up"])
        assert client.main() == 0
        assert "Remaining: 23" in capsys.readouterr().out
        assert "Actions: 1 / 24" in game.execute("show")
        monkeypatch.setattr(sys, "argv", ["play.py", "show"])
        assert client.main() == 0
        assert "Remaining: 23" in capsys.readouterr().out
        monkeypatch.setattr(sys, "argv", ["play.py", "history"])
        assert client.main() == 0
        assert json.loads(capsys.readouterr().out)["remaining"] == 23
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_stdio_round_trip_preserves_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    game = SokobanAuthority(tmp_path)
    gateway = load_module("test_stdio_gateway", ROOT / "docker" / "gateway.py")
    read_fd, write_fd = os.pipe()
    reader = os.fdopen(read_fd, "rb", buffering=0)
    writer = os.fdopen(write_fd, "wb", buffering=0)
    replies = queue.Queue()
    monkeypatch.setattr(gateway, "GAME_REPLIES", replies)
    monkeypatch.setattr(
        gateway, "print", lambda message, flush: writer.write((message + "\n").encode()),
        raising=False,
    )

    class Input:
        def write(self, value: bytes) -> None:
            replies.put(json.loads(value))

        def flush(self) -> None:
            pass

    process = type("Process", (), {"stdout": reader, "stdin": Input()})()
    closing = threading.Event()
    bridge = threading.Thread(target=network_guard.serve_game_requests, args=(process, game, closing))
    bridge.start()
    try:
        assert "Remaining: 24" in gateway.request_game("show")
        for _ in range(24):
            last = gateway.request_game("undo")
        assert "Remaining: 0" in last
        assert game.limit_reached.is_set()
        assert len(json.loads(game.path.read_text(encoding="utf-8"))["actions"]) == 24
    finally:
        closing.set()
        writer.close()
        bridge.join(timeout=3)
        reader.close()
    assert not bridge.is_alive()
    assert not game.failed.is_set()
