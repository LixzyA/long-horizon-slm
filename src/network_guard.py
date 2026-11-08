import json
import re
import subprocess
import sys
import threading
import time
from typing import Any

from sokoban_authority import SokobanAuthority
from llamacpp_config import PORT

IMAGE = "long-horizon-pi:1.4.0"

PROBE = r"""
import http.client, json, os, socket, sys, time
host = sys.argv[1]
def connects(address, port):
    try:
        with socket.create_connection((address, port), timeout=2): return True
    except OSError: return False
for _ in range(30):
    if connects("gateway", 8080) and connects("gateway", 3128): break
    time.sleep(0.2)
else: raise SystemExit("Gateway did not become ready")
if connects(host, __BACKEND_PORT__) or connects("1.1.1.1", 443):
    raise SystemExit("Direct network access was not blocked")
for path in ("/props", "/models/load", "/models/unload", "/completion"):
    conn = http.client.HTTPConnection("gateway", 8080, timeout=5)
    conn.request("POST", path, "{}", {"Authorization": "Bearer " + os.environ["PROBE_TOKEN"]})
    if conn.getresponse().status != 404: raise SystemExit("Management endpoint was not blocked")
    conn.close()
if os.environ.get("PROBE_SOKOBAN") == "1":
    conn = http.client.HTTPConnection("gateway", 8080, timeout=10)
    conn.request("POST", "/sokoban", json.dumps({"action": "show"}), {
        "Authorization": "Bearer " + os.environ["PROBE_TOKEN"],
        "Content-Type": "application/json",
    })
    response = conn.getresponse()
    text = response.read().decode("utf-8")
    limit = os.environ["PROBE_ACTION_LIMIT"]
    if response.status != 200 or f"Actions: 0 / {limit}" not in text or f"Remaining: {limit}" not in text:
        raise SystemExit("Sokoban game service was not verified")
    conn.close()
for target in ("127.0.0.1:443", host + ":443", "[::1]:443"):
    with socket.create_connection(("gateway", 3128), timeout=5) as sock:
        sock.sendall(("CONNECT " + target + " HTTP/1.1\r\nHost: " + target + "\r\n\r\n").encode())
        try: reply = sock.recv(256)
        except OSError: reply = b""
        if b" 200 " in reply: raise SystemExit("Private web destination was not blocked")
print("verified")
""".replace("__BACKEND_PORT__", str(PORT))


def verify_network_settings(settings: dict[str, Any]) -> bool:
    return (
        settings.get("Internal") is True
        and settings.get("EnableIPv6") is False
        and settings.get("Options", {}).get(
            "com.docker.network.bridge.gateway_mode_ipv4"
        )
        == "isolated"
    )


def run_docker(
    arguments: list[str], timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Docker {' '.join(arguments[:2])} failed: {result.stderr.strip()[:300]}"
        )
    return result


def resolve_image(image: str) -> str:
    image_id = run_docker(["image", "inspect", "--format", "{{.Id}}", image]).stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeError("Cannot identify the container image ID.")
    return image_id


def serve_game_requests(
    process: subprocess.Popen, game: SokobanAuthority, closing: threading.Event
) -> None:
    try:
        for line in process.stdout:
            request = json.loads(line)
            if (
                not isinstance(request, dict)
                or set(request) != {"type", "id", "action"}
                or request["type"] != "game_request"
                or not isinstance(request["id"], str)
                or not request["id"]
                or not isinstance(request["action"], str)
            ):
                raise ValueError("Invalid game request")
            try:
                response = {"id": request["id"], "ok": True, "output": game.execute(request["action"])}
            except (OSError, ValueError):
                game.failed.set()
                response = {"id": request["id"], "ok": False}
            process.stdin.write((json.dumps(response) + "\n").encode("utf-8"))
            process.stdin.flush()
            if game.failed.is_set():
                break
    except (OSError, ValueError, TypeError):
        game.failed.set()
    finally:
        if not closing.is_set():
            game.failed.set()


class GatewaySession:
    def __init__(
        self, name: str, token: str, model_path: str, thinking_mode: str = "high",
        game: SokobanAuthority | None = None,
        *, backend_token: str, image: str = IMAGE,
    ) -> None:
        self.network = name + "-network"
        self.gateway = name + "-gateway"
        self.token = token
        self.model_path = model_path
        self.backend_token = backend_token
        self.thinking_mode = thinking_mode
        self.game = game
        self.image = image
        self.closing = threading.Event()
        self.game_reader: threading.Thread | None = None
        self.network_created = False
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        run_docker(
            [
                "network",
                "create",
                "--internal",
                "-o",
                "com.docker.network.bridge.gateway_mode_ipv4=isolated",
                self.network,
            ]
        )
        self.network_created = True
        try:
            details = json.loads(
                run_docker(["network", "inspect", self.network]).stdout
            )
            if len(details) != 1 or not verify_network_settings(details[0]):
                raise RuntimeError(
                    "Docker did not create the required isolated network."
                )
            self.process = subprocess.Popen(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    self.network,
                    "--network-alias",
                    "gateway",
                    "--name",
                    self.gateway,
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=64",
                    "--memory=256m",
                    "--env",
                    "GATEWAY_TOKEN=" + self.token,
                    "--env",
                    "BACKEND_MODEL_PATH=" + self.model_path,
                    "--env",
                    "BACKEND_TOKEN=" + self.backend_token,
                    "--env",
                    "THINKING_MODE=" + self.thinking_mode,
                    "--env",
                    "SOKOBAN_ENABLED=" + ("1" if self.game is not None else "0"),
                    "--entrypoint",
                    "python",
                    self.image,
                    "-u",
                    "/opt/gateway.py",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE if self.game is not None else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if self.game is not None:
                self.game_reader = threading.Thread(
                    target=serve_game_requests,
                    args=(self.process, self.game, self.closing),
                    daemon=True,
                )
                self.game_reader.start()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("The network gateway exited during startup.")
                state = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", self.gateway],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if state.returncode == 0 and state.stdout.strip() == "true":
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("The network gateway did not start.")
            run_docker(["network", "connect", "bridge", self.gateway])
            command = "import sys,socket; sys.path.insert(0,'/opt'); import gateway; assert gateway.model_ready(), 'Backend identity or settings mismatch'; print(socket.gethostbyname('host.docker.internal'))"
            host = run_docker(
                ["exec", self.gateway, "python", "-c", command], timeout=15
            ).stdout.strip()
            result = run_docker(
                [
                    "run",
                    "--rm",
                    "--network",
                    self.network,
                    "--env",
                    "PROBE_SOKOBAN=" + ("1" if self.game is not None else "0"),
                    "--env",
                    "PROBE_ACTION_LIMIT=" + str(self.game.state["action_limit"] if self.game is not None else 0),
                    "--env",
                    "PROBE_TOKEN=" + self.token,
                    "--entrypoint",
                    "python",
                    self.image,
                    "-c",
                    PROBE,
                    host,
                ],
                timeout=30,
            )
            if result.stdout.strip() != "verified":
                raise RuntimeError("The network boundary could not be verified.")
        except BaseException:
            if not self.close():
                print(
                    f"Could not clean up gateway or network for {self.network}.",
                    file=sys.stderr,
                )
            raise

    def close(self) -> bool:
        ok = True
        self.closing.set()
        if self.process is not None:
            stopped = True
            try:
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
                self.process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    run_docker(["rm", "-f", self.gateway], timeout=15)
                    self.process.wait(timeout=5)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    stopped = False
                    ok = False
            if stopped:
                self.process = None
        if self.game_reader is not None:
            self.game_reader.join(timeout=5)
            if self.game_reader.is_alive():
                ok = False
            else:
                self.game_reader = None
        if self.network_created:
            try:
                run_docker(["network", "rm", self.network], timeout=15)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                ok = False
            else:
                self.network_created = False
        return ok
