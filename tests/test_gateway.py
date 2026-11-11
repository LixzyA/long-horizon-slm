import importlib.util
import io
import json
import socket
import threading
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import llamacpp_config as config

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
        {"model": "Qwen3.5-custom-32k", "reasoning_effort": "high"}
    )
    assert not gateway.valid_model_request(
        {"model": "Qwen3.5-custom-32k", "reasoning_effort": "none"}
    )
    assert not gateway.valid_model_request(
        {"model": "other", "reasoning_effort": "high"}
    )
    assert not gateway.valid_model_request(
        {"model": "Qwen3.5-custom-32k", "reasoning_effort": "high", "temperature": 0.3}
    )
    assert not gateway.valid_model_request(
        {
            "model": "Qwen3.5-custom-32k",
            "reasoning_effort": "high",
            "reasoning": {"effort": "none"},
        }
    )
    assert not gateway.valid_model_request(
        {
            "model": "Qwen3.5-custom-32k",
            "reasoning_effort": "high",
            "options": {"temperature": 0.3},
        }
    )


def test_game_endpoint_accepts_only_authorized_single_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_TOKEN", "token")
    monkeypatch.setenv("SOKOBAN_ENABLED", "1")
    calls = []
    monkeypatch.setattr(gateway, "request_game", lambda action: calls.append(action) or "Remaining: 23")
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.ModelHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/sokoban"

    def request(token: str, body: dict) -> urllib.request.Request:
        return urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + token},
        )

    try:
        for token, body, status in [
            ("wrong", {"action": "up"}, 403),
            ("token", {"action": "init"}, 400),
            ("token", {"action": "up", "reset": True}, 400),
        ]:
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request(token, body), timeout=3)
            assert error.value.code == status
        with urllib.request.urlopen(request("token", {"action": "up"}), timeout=3) as response:
            assert response.read() == b"Remaining: 23"
        assert calls == ["up"]
        monkeypatch.setenv("SOKOBAN_ENABLED", "0")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request("token", {"action": "show"}), timeout=3)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
@pytest.mark.parametrize("mode", ["high", "off"])
@pytest.mark.parametrize("upstream_status", [200, 503])
def test_model_gateway_forwards_only_authorized_thinking_inference(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    upstream_status: int,
) -> None:
    seen = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            assert self.headers.get("Authorization") == "Bearer private-backend-token"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body))
            self.send_response(upstream_status)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: done\n\n")

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setenv("GATEWAY_TOKEN", "token")
    monkeypatch.setenv("THINKING_MODE", mode)
    monkeypatch.setenv("BACKEND_TOKEN", "private-backend-token")
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

    valid = {"model": "Qwen3.5-custom-32k"}
    if mode == "high":
        valid["reasoning_effort"] = "high"
    try:
        for path, token, body, status in [
            ("/api/delete", "token", valid, 404),
            ("/props", "token", valid, 404),
            ("/models/load", "token", valid, 404),
            ("/models/unload", "token", valid, 404),
            ("/completion", "token", valid, 404),
            ("/v1/chat/completions", "wrong", valid, 403),
            ("/v1/chat/completions", "token", {"model": "other"}, 400),
        ]:
            with pytest.raises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request(path, token, body), timeout=3)
            assert rejected.value.code == status
        client = gateway.http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            client.request("POST", "/v1/chat/completions", json.dumps(valid), {"Authorization": "Bearer token"})
            response = client.getresponse()
            assert response.status == upstream_status
            assert response.read() == b"data: done\n\n"
        finally:
            client.close()
        expected = {
            **valid, **config.SAMPLING, "model": config.ALIAS, "samplers": config.SAMPLERS,
            "reasoning_effort": "none" if mode == "off" else "high",
            "chat_template_kwargs": {"enable_thinking": mode == "high"}, "reasoning_format": "deepseek",
        }
        assert seen == [("/v1/chat/completions", expected)]
        monkeypatch.setattr(gateway, "model_ready", lambda: False)
        with pytest.raises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(request("/v1/chat/completions", "token", valid), timeout=3)
        assert rejected.value.code == 503
        assert len(seen) == 1
    finally:
        server.shutdown()
        server.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_off_mode_rejects_requests_that_enable_thinking() -> None:
    assert gateway.valid_model_request({"model": "Qwen3.5-custom-32k"}, "off")
    assert gateway.valid_model_request(
        {"model": "Qwen3.5-custom-32k", "reasoning_effort": "none"}, "off"
    )
    assert not gateway.valid_model_request(
        {"model": "Qwen3.5-custom-32k", "reasoning_effort": "high"}, "off"
    )
    assert not gateway.valid_model_request({"model": "Qwen3.5-custom-32k"}, "invalid")


@pytest.mark.parametrize(
    ("context", "expected"), [(32767, False), (32768, True), (32769, False)]
)
def test_model_ready_requires_exact_context(
    monkeypatch: pytest.MonkeyPatch, context: int, expected: bool
) -> None:
    template = "test template"
    import hashlib
    monkeypatch.setattr(config, "TEMPLATE_SHA256", hashlib.sha256(template.encode()).hexdigest())
    def open_url(request: object, timeout: int):
        url = request.full_url if hasattr(request, "full_url") else request
        assert request.get_header("Authorization") == "Bearer private-token"
        value = {"status": "ok"}
        if url.endswith("/props"):
            value = {
                "total_slots": 1, "model_path": "C:/model.gguf", "chat_template": template,
                "default_generation_settings": {"n_ctx": context, "params": {**config.SAMPLING, "samplers": config.SAMPLERS}},
            }
        if url.endswith("/v1/models"):
            value = {"data": [{"id": config.ALIAS}]}
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setenv("BACKEND_TOKEN", "private-token")
    monkeypatch.setenv("BACKEND_MODEL_PATH", "C:/model.gguf")
    class Opener:
        open = staticmethod(open_url)
    monkeypatch.setattr(gateway.urllib.request, "build_opener", lambda *args: Opener())
    assert gateway.model_ready() is expected


@pytest.mark.parametrize("send_headers", [False, True])
def test_disconnected_client_cancels_a_quiet_upstream(monkeypatch: pytest.MonkeyPatch, send_headers: bool) -> None:
    started = threading.Event()
    disconnected = threading.Event()

    class Upstream(gateway.QuietHandler):
        def do_POST(self) -> None:
            assert self.headers["Authorization"] == "Bearer private-key"
            self.rfile.read(int(self.headers["Content-Length"]))
            if send_headers:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
            started.set()
            self.connection.settimeout(4)
            try:
                remaining = self.connection.recv(1)
            except ConnectionResetError:
                remaining = b""
            if remaining == b"":
                disconnected.set()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.ModelHandler)
    for service in (upstream, server):
        service.daemon_threads = True
        threading.Thread(target=service.serve_forever, daemon=True).start()
    monkeypatch.setenv("GATEWAY_TOKEN", "token")
    monkeypatch.setenv("BACKEND_TOKEN", "private-key")
    monkeypatch.setenv("THINKING_MODE", "high")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setattr(gateway, "model_ready", lambda: True)
    monkeypatch.setattr(gateway, "MODEL_ENDPOINT", f"http://127.0.0.1:{upstream.server_port}/v1/chat/completions")
    body = json.dumps({"model": config.MODEL, "reasoning_effort": "high", "stream": True}).encode()
    try:
        with socket.create_connection(server.server_address, timeout=3) as client:
            client.sendall(b"POST /v1/chat/completions HTTP/1.0\r\nAuthorization: Bearer token\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
            assert started.wait(3)
            client.shutdown(socket.SHUT_RDWR)
        assert disconnected.wait(3), "A quiet upstream remained open after the client disconnected"
    finally:
        for service in (server, upstream):
            service.shutdown()
            service.server_close()


def test_backend_readiness_ignores_inherited_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    template = "test template"
    monkeypatch.setattr(config, "TEMPLATE_SHA256", hashlib.sha256(template.encode()).hexdigest())

    class Upstream(gateway.QuietHandler):
        def do_GET(self) -> None:
            assert self.headers["Authorization"] == "Bearer private-key"
            value = {
                "/health": {"status": "ok"},
                "/v1/models": {"data": [{"id": config.ALIAS}]},
                "/props": {"total_slots": 1, "model_path": "C:/model.gguf", "chat_template": template,
                           "default_generation_settings": {"n_ctx": 32768, "params": {**config.SAMPLING, "samplers": config.SAMPLERS}}},
            }[self.path]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setattr(gateway, "BACKEND", f"http://127.0.0.1:{upstream.server_port}")
    monkeypatch.setenv("BACKEND_TOKEN", "private-key")
    monkeypatch.setenv("BACKEND_MODEL_PATH", "C:/model.gguf")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    try:
        assert gateway.model_ready()
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_openrouter_request_is_fixed_to_requested_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_KIND", "openrouter")
    body = {"model": gateway.OPENROUTER_MODEL, "reasoning": {"effort": "high"}, "messages": []}
    assert gateway.valid_model_request(body, "high")
    assert not gateway.valid_model_request({**body, "model": "other"}, "high")
    assert not gateway.valid_model_request({**body, "reasoning": {"effort": "none"}}, "high")
    assert not gateway.valid_model_request({**body, "provider": {"order": ["other"]}}, "high")
    assert gateway.prepare_model_request(body, "high") == {**body, "max_tokens": 16384}
    assert "samplers" not in gateway.prepare_model_request(body, "high")


def test_openrouter_forwards_with_private_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append((self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"data: done\n\n")

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setenv("BACKEND_KIND", "openrouter")
    monkeypatch.setenv("GATEWAY_TOKEN", "agent-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-key")
    monkeypatch.setenv("THINKING_MODE", "high")
    monkeypatch.setattr(gateway, "OPENROUTER_ENDPOINT", f"https://127.0.0.1:{upstream.server_port}/v1/chat/completions")
    monkeypatch.setattr(gateway.http.client, "HTTPSConnection", gateway.http.client.HTTPConnection)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.ModelHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    body = {"model": gateway.OPENROUTER_MODEL, "reasoning": {"effort": "high"}, "messages": []}
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer agent-token"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.read() == b"data: done\n\n"
        assert seen == [("Bearer private-key", {**body, "max_tokens": 16384})]
    finally:
        server.shutdown()
        server.server_close()
        upstream.shutdown()
        upstream.server_close()


@pytest.mark.parametrize("mode,effort", [("high", "high"), ("off", None)])
def test_huggingface_request_uses_only_the_selected_model(monkeypatch: pytest.MonkeyPatch, mode: str, effort: str | None) -> None:
    monkeypatch.setenv("BACKEND_KIND", "huggingface")
    body = {"model": gateway.HUGGINGFACE_MODEL, "messages": [], "reasoning_effort": effort}
    assert gateway.valid_model_request(body, mode)
    assert not gateway.valid_model_request({**body, "model": "other"}, mode)
    assert not gateway.valid_model_request({**body, "temperature": 0.1}, mode)
    assert not gateway.valid_model_request({**body, "reasoning_effort": "none" if mode == "high" else "high"}, mode)
    result = gateway.prepare_model_request(body, mode)
    assert result["model"] == gateway.HUGGINGFACE_MODEL
    assert result["reasoning_effort"] == ("high" if mode == "high" else "none")
    assert "samplers" not in result


def test_huggingface_forwards_to_router_with_private_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"data: done\n\n")
        def log_message(self, format: str, *args: object) -> None:
            pass
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setenv("BACKEND_KIND", "huggingface")
    monkeypatch.setenv("GATEWAY_TOKEN", "agent-token")
    monkeypatch.setenv("HF_TOKEN", "private-key")
    monkeypatch.setenv("THINKING_MODE", "high")
    monkeypatch.setattr(gateway, "HUGGINGFACE_ENDPOINT", f"https://127.0.0.1:{upstream.server_port}/v1/chat/completions")
    monkeypatch.setattr(gateway.http.client, "HTTPSConnection", gateway.http.client.HTTPConnection)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway.ModelHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    body = {"model": gateway.HUGGINGFACE_MODEL, "reasoning_effort": "high", "messages": []}
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer agent-token"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.read() == b"data: done\n\n"
        assert seen == [("/v1/chat/completions", "Bearer private-key", {**body, "max_tokens": 16384})]
    finally:
        server.shutdown()
        server.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_huggingface_readiness_checks_token_without_inherited_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_KIND", "huggingface")
    monkeypatch.setenv("HF_TOKEN", "private-key")
    seen = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Opener:
        def open(self, request, timeout):
            seen.append((request.full_url, request.get_header("Authorization"), timeout))
            return Response()
    def build_opener(handler):
        assert isinstance(handler, urllib.request.ProxyHandler)
        assert handler.proxies == {}
        return Opener()
    monkeypatch.setattr(gateway.urllib.request, "build_opener", build_opener)
    assert gateway.model_ready()
    assert seen == [("https://huggingface.co/api/whoami-v2", "Bearer private-key", 15)]


@pytest.mark.parametrize(
    "kind,model,reasoning",
    [("openrouter", gateway.OPENROUTER_MODEL, {"reasoning": {"effort": "high"}}),
     ("huggingface", gateway.HUGGINGFACE_MODEL, {"reasoning_effort": "high"})],
)
def test_hosted_requests_apply_output_limit_when_omitted(
    monkeypatch: pytest.MonkeyPatch, kind: str, model: str, reasoning: dict,
) -> None:
    monkeypatch.setenv("BACKEND_KIND", kind)
    body = {"model": model, "messages": [], **reasoning}
    assert gateway.valid_model_request(body, "high")
    assert gateway.prepare_model_request(body, "high")["max_tokens"] == 16384
    assert "max_tokens" not in body
    assert gateway.prepare_model_request({**body, "max_tokens": 7}, "high")["max_tokens"] == 7
    for value in (0, 16385, True, None):
        assert not gateway.valid_model_request({**body, "max_tokens": value}, "high")
