import hmac
import ipaddress
import json
import os
import select
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "Qwen3.5-custom-32k"
OLLAMA = "http://host.docker.internal:11434"
MODEL_ENDPOINT = OLLAMA + "/v1/chat/completions"
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
    if (
        not isinstance(body, dict)
        or body.get("model") != MODEL
        or not set(body).issubset(MODEL_FIELDS)
    ):
        return False
    effort = body.get("reasoning_effort")
    if thinking_mode == "off":
        return effort is None or effort == "none"
    return thinking_mode == "high" and effort == "high"


def model_ready() -> bool:
    data = json.dumps(
        {"model": MODEL, "prompt": "", "stream": False, "keep_alive": "10m"}
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA + "/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        json.load(response)
    with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=10) as response:
        models = json.load(response).get("models", [])
    return any(
        item.get("name") in (MODEL, MODEL + ":latest")
        and item.get("digest") == os.environ["MODEL_DIGEST"]
        and isinstance(item.get("context_length"), int)
        and item["context_length"] == 32768
        for item in models
    )


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


class ModelHandler(QuietHandler):
    def do_POST(self) -> None:
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
            if thinking_mode == "off":
                body["reasoning_effort"] = "none"
            raw = json.dumps(body).encode("utf-8")
            if not model_ready():
                self.send_error(503, "Model identity or context could not be verified")
                return
            request = urllib.request.Request(
                MODEL_ENDPOINT,
                data=raw,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=1800) as upstream:
                self.send_response(upstream.status)
                self.send_header(
                    "Content-Type",
                    upstream.headers.get("Content-Type", "application/json"),
                )
                self.send_header("Connection", "close")
                self.end_headers()
                while chunk := upstream.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            self.send_header(
                "Content-Type", exc.headers.get("Content-Type", "text/plain")
            )
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(exc.read(65536))
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            self.close_connection = True


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
    sys.stdin.buffer.read()
    for server in servers:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
