import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "gateway", Path(__file__).resolve().parents[1] / "docker" / "gateway.py"
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "169.254.169.254",
        "192.168.65.254",
        "100.64.0.1",
        "::1",
        "224.0.0.1",
        "64:ff9b::7f00:1",
    ],
)
def test_web_gateway_rejects_private_destinations(address: str) -> None:
    with pytest.raises(ValueError):
        gateway.public_destination(address, 443)


def test_web_gateway_rejects_dns_answers_mixing_public_and_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway, "resolve_domain", lambda host: ["93.184.216.34", "127.0.0.1"]
    )
    with pytest.raises(ValueError):
        gateway.public_destination("example.test", 443)


def test_web_gateway_pins_the_validated_public_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway, "resolve_domain", lambda host: ["93.184.216.34"])
    assert gateway.public_destination("example.test", 443)[0][-1] == (
        "93.184.216.34",
        443,
    )


def test_model_gateway_only_accepts_thinking_for_the_selected_model() -> None:
    assert gateway.valid_model_request(
        {"model": "qwen-custom", "reasoning_effort": "high"}
    )
    assert not gateway.valid_model_request(
        {"model": "qwen-custom", "reasoning_effort": "none"}
    )
    assert not gateway.valid_model_request(
        {"model": "other", "reasoning_effort": "high"}
    )
    assert not gateway.valid_model_request(
        {"model": "qwen-custom", "reasoning_effort": "high", "temperature": 0.3}
    )
    assert not gateway.valid_model_request(
        {
            "model": "qwen-custom",
            "reasoning_effort": "high",
            "reasoning": {"effort": "none"},
        }
    )
    assert not gateway.valid_model_request(
        {
            "model": "qwen-custom",
            "reasoning_effort": "high",
            "options": {"temperature": 0.3},
        }
    )


@pytest.mark.parametrize("mode", ["high", "off"])
def test_model_gateway_forwards_only_authorized_thinking_inference(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    seen = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: done\n\n")

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setenv("GATEWAY_TOKEN", "token")
    monkeypatch.setenv("THINKING_MODE", mode)
    monkeypatch.setattr(
        gateway,
        "MODEL_ENDPOINT",
        f"http://127.0.0.1:{upstream.server_port}/v1/chat/completions",
    )
    monkeypatch.setattr(gateway, "model_ready", lambda: True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.ModelHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path: str, token: str, body: dict) -> urllib.request.Request:
        return urllib.request.Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + token},
        )

    valid = {"model": "qwen-custom"}
    if mode == "high":
        valid["reasoning_effort"] = "high"
    try:
        for path, token, body, status in [
            ("/api/delete", "token", valid, 404),
            ("/v1/chat/completions", "wrong", valid, 403),
            ("/v1/chat/completions", "token", {"model": "other"}, 400),
        ]:
            with pytest.raises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request(path, token, body), timeout=3)
            assert rejected.value.code == status
        with urllib.request.urlopen(
            request("/v1/chat/completions", "token", valid), timeout=3
        ) as response:
            assert response.read() == b"data: done\n\n"
        expected = {**valid, "reasoning_effort": "none" if mode == "off" else "high"}
        assert seen == [("/v1/chat/completions", expected)]
    finally:
        server.shutdown()
        server.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_off_mode_rejects_requests_that_enable_thinking() -> None:
    assert gateway.valid_model_request({"model": "qwen-custom"}, "off")
    assert gateway.valid_model_request(
        {"model": "qwen-custom", "reasoning_effort": "none"}, "off"
    )
    assert not gateway.valid_model_request(
        {"model": "qwen-custom", "reasoning_effort": "high"}, "off"
    )
    assert not gateway.valid_model_request({"model": "qwen-custom"}, "invalid")
