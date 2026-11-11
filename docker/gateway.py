import hmac
import http.client
import ipaddress
import json
import os
import queue
import select
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import llamacpp_config as config

MODEL = config.MODEL
OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash-1017"
HUGGINGFACE_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
HUGGINGFACE_ENDPOINT = "https://router.huggingface.co/v1/chat/completions"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
BACKEND = f"http://host.docker.internal:{config.PORT}"
MODEL_ENDPOINT = BACKEND + "/v1/chat/completions"
MODEL_FIELDS = {
    "model",
    "messages",
    "stream",
    "stream_options",
    "tools",
    "tool_choice",
    "max_tokens",
    "reasoning_effort",
}
GAME_LOCK = threading.Lock()
GAME_REPLIES = queue.Queue()


def request_game(action: str) -> str:
    with GAME_LOCK:
        request_id = uuid.uuid4().hex
        print(json.dumps({"type": "game_request", "id": request_id, "action": action}), flush=True)
        deadline = time.monotonic() + 30
        while True:
            try:
                reply = GAME_REPLIES.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise TimeoutError("Game request timed out; use show to check its state") from exc
            if reply.get("id") == request_id:
                if not reply.get("ok") or not isinstance(reply.get("output"), str):
                    raise RuntimeError("Game service failed")
                return reply["output"]


def resolve_domain(host: str) -> list[str]:
    domain = host.rstrip(".").encode("idna").decode("ascii").lower()
    labels = domain.split(".")
    if (
        len(domain) > 253
        or len(labels) < 2
        or domain.endswith((".local", ".localhost", ".internal"))
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(c.isascii() and (c.isalnum() or c == "-") for c in label)
            for label in labels
        )
    ):
        raise ValueError("Invalid public hostname")
    addresses = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for kind, record_type in (("A", 1), ("AAAA", 28)):
        query = urllib.parse.urlencode({"name": domain, "type": kind})
        request = urllib.request.Request(
            "https://1.1.1.1/dns-query?" + query,
            headers={"Accept": "application/dns-json"},
        )
        with opener.open(request, timeout=8) as response:
            result = json.loads(response.read(65536))
        if result.get("Status") not in (0, 3):
            raise ValueError("Public DNS lookup failed")
        for answer in result.get("Answer", []):
            if answer.get("type") == record_type:
                addresses.append(answer["data"])
    return addresses


def public_destination(host: str, port: int) -> list[tuple]:
    if port not in (80, 443):
        raise ValueError("Only public web ports are allowed")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolve_domain(host)
    if not addresses:
        raise ValueError("No address")
    targets = []
    for value in addresses:
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if (
            not address.is_global
            or address.is_multicast
            or (
                isinstance(address, ipaddress.IPv6Address)
                and (
                    address.sixtofour
                    or address.teredo
                    or address in ipaddress.ip_network("64:ff9b::/96")
                )
            )
        ):
            raise ValueError("Non-public address")
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        target = (
            (str(address), port, 0, 0)
            if family == socket.AF_INET6
            else (str(address), port)
        )
        targets.append((family, socket.SOCK_STREAM, 0, "", target))
    return targets


def valid_model_request(body: object, thinking_mode: str = "high") -> bool:
    kind = os.environ.get("BACKEND_KIND", "llamacpp")
    openrouter = kind == "openrouter"
    selected_model = OPENROUTER_MODEL if openrouter else HUGGINGFACE_MODEL if kind == "huggingface" else MODEL
    fields = (MODEL_FIELDS - {"reasoning_effort"}) | {"reasoning"} if openrouter else MODEL_FIELDS
    if (
        not isinstance(body, dict)
        or body.get("model") != selected_model
        or not set(body).issubset(fields)
    ):
        return False
    if openrouter:
        reasoning = body.get("reasoning")
        if reasoning != {"effort": "none" if thinking_mode == "off" else "high"}:
            return False
        effort = "none" if thinking_mode == "off" else "high"
    else:
        effort = body.get("reasoning_effort")
    max_tokens = body.get("max_tokens", 16384)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 16384:
        return False
    if thinking_mode == "off":
        return effort is None or effort == "none"
    return thinking_mode == "high" and effort == "high"


def prepare_model_request(body: dict, thinking_mode: str) -> dict:
    body = dict(body)
    kind = os.environ.get("BACKEND_KIND", "llamacpp")
    if kind in ("openrouter", "huggingface"):
        body.setdefault("max_tokens", 16384)
    if kind != "openrouter" and thinking_mode == "off":
        body["reasoning_effort"] = "none"
    if kind == "llamacpp":
        body.update(config.SAMPLING)
        body["samplers"] = config.SAMPLERS
        body["model"] = config.ALIAS
        body["chat_template_kwargs"] = {"enable_thinking": thinking_mode == "high"}
        body["reasoning_format"] = "deepseek"
    return body


def model_ready() -> bool:
    if os.environ.get("BACKEND_KIND") == "huggingface":
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            request = urllib.request.Request(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": "Bearer " + os.environ["HF_TOKEN"]},
            )
            with opener.open(request, timeout=15) as response:
                return response.status == 200
        except (OSError, KeyError):
            return False
    if os.environ.get("BACKEND_KIND") == "openrouter":
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
            )
            with opener.open(request, timeout=15) as response:
                return response.status == 200
        except (OSError, KeyError):
            return False
    try:
        responses = []
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path in ("/health", "/props", "/v1/models"):
            request = urllib.request.Request(BACKEND + path, headers={"Authorization": "Bearer " + os.environ["BACKEND_TOKEN"]})
            with opener.open(request, timeout=5) as response:
                responses.append(json.load(response))
        if not isinstance(responses[0], dict) or responses[0].get("status") != "ok":
            return False
        config.validate_properties(responses[1], os.environ["BACKEND_MODEL_PATH"])
        config.validate_models(responses[2])
        return True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        return False


def connect_public(host: str, port: int) -> socket.socket:
    addresses = public_destination(host, port)
    last_error = None
    for family, kind, protocol, _, target in addresses:
        connection = socket.socket(family, kind, protocol)
        try:
            connection.settimeout(15)
            connection.connect(target)
            return connection
        except OSError as exc:
            connection.close()
            last_error = exc
    raise OSError("Unable to reach public web host") from last_error


def pump(left: socket.socket, right: socket.socket) -> None:
    left.setblocking(False)
    right.setblocking(False)
    while True:
        ready, _, errors = select.select([left, right], [], [left, right], 30)
        if errors or not ready:
            return
        for source in ready:
            data = source.recv(65536)
            if not data:
                return
            target = right if source is left else left
            target.setblocking(True)
            target.settimeout(15)
            target.sendall(data)
            target.setblocking(False)


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def cancel_on_disconnect(client: socket.socket, upstream: socket.socket, done: threading.Event) -> None:
    try:
        while not done.is_set():
            readable, _, errors = select.select([client], [], [client], 0.1)
            if errors or (readable and not client.recv(1, socket.MSG_PEEK)):
                break
            if readable:
                done.wait(0.1)
    except OSError:
        pass
    if not done.is_set():
        try:
            upstream.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


class ModelHandler(QuietHandler):
    def do_POST(self) -> None:
        if self.path == "/sokoban" and os.environ.get("SOKOBAN_ENABLED") == "1":
            self.game_action()
            return
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        if not hmac.compare_digest(
            self.headers.get("Authorization", ""),
            "Bearer " + os.environ["GATEWAY_TOKEN"],
        ):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32 * 1024 * 1024:
                self.send_error(413)
                return
            body = json.loads(self.rfile.read(length))
            thinking_mode = os.environ["THINKING_MODE"]
            if not valid_model_request(body, thinking_mode):
                self.send_error(
                    400, "Model request does not match the experiment settings"
                )
                return
            kind = os.environ.get("BACKEND_KIND", "llamacpp")
            hosted = kind in ("openrouter", "huggingface")
            raw = json.dumps(prepare_model_request(body, thinking_mode)).encode("utf-8")
            if not hosted and not model_ready():
                self.send_error(503, "Model identity or context could not be verified")
                return
            endpoint = urllib.parse.urlsplit(
                OPENROUTER_ENDPOINT if kind == "openrouter" else HUGGINGFACE_ENDPOINT if kind == "huggingface" else MODEL_ENDPOINT
            )
            connection_type = http.client.HTTPSConnection if hosted else http.client.HTTPConnection
            connection = connection_type(endpoint.hostname, endpoint.port, timeout=1800)
            done = threading.Event()
            watcher = None
            cancel_socket = None
            try:
                connection.request(
                    "POST", endpoint.path, body=raw,
                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY" if kind == "openrouter" else "HF_TOKEN" if kind == "huggingface" else "BACKEND_TOKEN"]},
                )
                # HTTPConnection closes its socket wrapper for close-delimited responses.
                cancel_socket = (socket.socket(fileno=os.dup(connection.sock.fileno()))
                                 if isinstance(connection.sock, ssl.SSLSocket) else connection.sock.dup())
                watcher = threading.Thread(target=cancel_on_disconnect, args=(self.connection, cancel_socket, done), daemon=True)
                watcher.start()
                with connection.getresponse() as upstream:
                    self.send_response(upstream.status)
                    self.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    while chunk := upstream.read1(65536):
                        self.wfile.write(chunk)
                        self.wfile.flush()
            finally:
                done.set()
                connection.close()
                if watcher is not None:
                    watcher.join(timeout=1)
                if cancel_socket is not None:
                    cancel_socket.close()
        except (OSError, ValueError, KeyError, http.client.HTTPException):
            self.close_connection = True

    def game_action(self) -> None:
        if not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + os.environ["GATEWAY_TOKEN"]
        ):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1024:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(length))
            if (
                not isinstance(body, dict)
                or set(body) != {"action"}
                or body["action"] not in ("show", "history", "up", "down", "left", "right", "undo")
            ):
                raise ValueError("Invalid game action")
        except (ValueError, TypeError):
            self.send_error(400)
            return
        try:
            output = request_game(body["action"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        except (OSError, RuntimeError):
            self.send_error(503, "Game service unavailable")


class WebHandler(QuietHandler):
    def do_CONNECT(self) -> None:
        try:
            parsed = urllib.parse.urlsplit("//" + self.path)
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Invalid destination")
            port = parsed.port or 443
            if port != 443:
                raise ValueError("Only HTTPS tunnels are allowed")
            with connect_public(parsed.hostname, port) as upstream:
                self.send_response(200, "Connection established")
                self.end_headers()
                pump(self.connection, upstream)
        except (OSError, ValueError):
            self.close_connection = True

    def do_GET(self) -> None:
        self._plain_web()

    def do_HEAD(self) -> None:
        self._plain_web()

    def _plain_web(self) -> None:
        try:
            parsed = urllib.parse.urlsplit(self.path)
            if (
                parsed.scheme != "http"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
            ):
                raise ValueError("Invalid URL")
            port = parsed.port or 80
            if (
                port != 80
                or self.headers.get("Transfer-Encoding")
                or self.headers.get("Content-Length", "0") != "0"
            ):
                raise ValueError("Invalid request")
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            with connect_public(parsed.hostname, port) as upstream:
                headers = [
                    f"{self.command} {target} HTTP/1.0",
                    f"Host: {parsed.netloc}",
                ]
                for name, value in self.headers.items():
                    if name.lower() not in (
                        "host",
                        "connection",
                        "proxy-connection",
                        "proxy-authorization",
                        "transfer-encoding",
                        "content-length",
                    ):
                        headers.append(f"{name}: {value}")
                upstream.sendall(
                    ("\r\n".join(headers) + "\r\n\r\n").encode("iso-8859-1")
                )
                while data := upstream.recv(65536):
                    self.connection.sendall(data)
        except (OSError, ValueError, UnicodeError):
            self.close_connection = True


def main() -> None:
    address = socket.gethostbyname(socket.gethostname())
    servers = [
        ThreadingHTTPServer((address, 8080), ModelHandler),
        ThreadingHTTPServer((address, 3128), WebHandler),
    ]
    for server in servers:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
    if os.environ.get("SOKOBAN_ENABLED") == "1":
        for line in sys.stdin:
            try:
                reply = json.loads(line)
                if isinstance(reply, dict):
                    GAME_REPLIES.put(reply)
            except ValueError:
                continue
    else:
        sys.stdin.buffer.read()
    for server in servers:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
