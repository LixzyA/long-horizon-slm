import json
import subprocess
import sys
import time
from typing import Any

IMAGE = "long-horizon-pi:1.4.0"

PROBE = r"""
import http.client, socket, sys, time
host = sys.argv[1]
def connects(address, port):
    try:
        with socket.create_connection((address, port), timeout=2): return True
    except OSError: return False
for _ in range(30):
    if connects("gateway", 8080) and connects("gateway", 3128): break
    time.sleep(0.2)
else: raise SystemExit("Gateway did not become ready")
if connects(host, 11434) or connects("1.1.1.1", 443):
    raise SystemExit("Direct network access was not blocked")
conn = http.client.HTTPConnection("gateway", 8080, timeout=5)
conn.request("POST", "/api/delete", "{}")
if conn.getresponse().status != 404: raise SystemExit("Management endpoint was not blocked")
conn.close()
for target in ("127.0.0.1:443", host + ":443", "[::1]:443"):
    with socket.create_connection(("gateway", 3128), timeout=5) as sock:
        sock.sendall(("CONNECT " + target + " HTTP/1.1\r\nHost: " + target + "\r\n\r\n").encode())
        try: reply = sock.recv(256)
        except OSError: reply = b""
        if b" 200 " in reply: raise SystemExit("Private web destination was not blocked")
print("verified")
"""


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


class GatewaySession:
    def __init__(
        self, name: str, token: str, digest: str, thinking_mode: str = "high"
    ) -> None:
        self.network = name + "-network"
        self.gateway = name + "-gateway"
        self.token = token
        self.digest = digest
        self.thinking_mode = thinking_mode
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
                    "MODEL_DIGEST=" + self.digest,
                    "--env",
                    "THINKING_MODE=" + self.thinking_mode,
                    "--entrypoint",
                    "python",
                    IMAGE,
                    "-u",
                    "/opt/gateway.py",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
            command = "import socket,urllib.request; print(socket.gethostbyname('host.docker.internal')); urllib.request.urlopen('http://host.docker.internal:11434/api/tags',timeout=5).close()"
            host = run_docker(
                ["exec", self.gateway, "python", "-c", command], timeout=15
            ).stdout.strip()
            result = run_docker(
                [
                    "run",
                    "--rm",
                    "--network",
                    self.network,
                    "--entrypoint",
                    "python",
                    IMAGE,
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
        if self.process is not None:
            try:
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
                self.process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    run_docker(["rm", "-f", self.gateway], timeout=15)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    ok = False
            self.process = None
        if self.network_created:
            try:
                run_docker(["network", "rm", self.network], timeout=15)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                ok = False
            self.network_created = False
        return ok
