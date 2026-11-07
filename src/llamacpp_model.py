"""Own the one Windows llama.cpp server used by an experiment."""

import ctypes
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

import llamacpp_config as config
import windows_job

BASE = f"http://127.0.0.1:{config.PORT}"


def locked_file(path: Path) -> BinaryIO:
    """Deny writes and replacement until the experiment releases the handle."""
    import msvcrt

    dll = windows_job.kernel32()
    dll.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    dll.CreateFileW.restype = wintypes.HANDLE
    handle = dll.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        dll.CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb")


def server_environment(directory: Path, token: str) -> dict[str, str]:
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("LLAMA_")}
    for name in ("APPDATA", "PROGRAMDATA"):
        root = directory / name.lower()
        root.mkdir(parents=True, exist_ok=False)
        environment[name] = str(root)
    environment["LLAMA_API_KEY"] = token
    return environment


def request_json(path: str, token: str, timeout: float = 5) -> dict:
    request = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("Invalid llama.cpp response")
    return value


def server_command(executable: Path, model: Path) -> list[str]:
    return [
        str(executable), "--model", str(model), "--alias", config.ALIAS,
        "--host", "0.0.0.0", "--port", str(config.PORT),
        "--ctx-size", str(config.CONTEXT_LENGTH), "--parallel", "1",
        "--jinja", "--reasoning-format", "deepseek", "--no-context-shift",
        "--n-predict", "16384", "--n-gpu-layers", "99",
        "--cache-type-k", "f16", "--cache-type-v", "f16", "--no-agent", "--no-ui-mcp-proxy",
        "--verbosity", "4", "--log-colors", "off", "--offline",
        "--temp", "1", "--top-k", "20", "--top-p", "0.95", "--min-p", "0",
        "--repeat-penalty", "1.15", "--presence-penalty", "1.5",
        "--frequency-penalty", "0", "--repeat-last-n", "64", "--seed", "-1",
        "--samplers", ";".join(config.SAMPLERS),
    ]


class LlamaServer:
    def __init__(self, executable: Path, model: Path, run_dir: Path) -> None:
        self.executable = executable.resolve(strict=True)
        self.model = model.resolve(strict=True)
        self.run_dir = run_dir
        self.token = secrets.token_urlsafe(32)
        self.process: subprocess.Popen | None = None
        self.reader: threading.Thread | None = None
        self.job = None
        self.files: list[BinaryIO] = []
        self.info: dict[str, Any] = {}
        self.log_failed = threading.Event()
        self.closing = False

    def check_alive(self) -> None:
        if self.log_failed.is_set():
            raise RuntimeError("llama.cpp log capture failed")
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("llama.cpp exited unexpectedly")

    def verify(self, deadline: float | None = None) -> dict:
        self.check_alive()

        def read(path: str) -> dict:
            remaining = 5 if deadline is None else min(5, deadline - time.monotonic())
            if remaining <= 0:
                raise RuntimeError("llama.cpp readiness deadline expired")
            return request_json(path, self.token, timeout=remaining)

        properties = config.validate_properties(read("/props"), str(self.model))
        config.validate_models(read("/v1/models"))
        if deadline is not None and time.monotonic() > deadline:
            raise RuntimeError("llama.cpp readiness deadline expired")
        return properties

    def start(self, startup_seconds: float = 120) -> dict:
        try:
            with socket.socket() as reservation:
                reservation.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                reservation.bind(("0.0.0.0", config.PORT))
            environment = server_environment(self.run_dir / "backend-config", self.token)
            runtime_hashes = {}
            for path in [self.executable, *sorted(self.executable.parent.glob("*.dll")), self.model]:
                file = locked_file(path)
                self.files.append(file)
                digest = hashlib.file_digest(file, "sha256").hexdigest()
                if path == self.model:
                    if digest != config.MODEL_SHA256:
                        raise RuntimeError("GGUF hash does not match the selected experiment model")
                else:
                    runtime_hashes[path.name] = digest
            version = subprocess.run(
                [str(self.executable), "--version"], env=environment, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW, check=True,
            )
            version_text = (version.stdout + version.stderr).replace(self.token, "<redacted>").strip()
            if "cd959bae9" not in version_text or "12110" not in version_text:
                raise RuntimeError("llama.cpp build does not match the pinned b12110 runtime")
            command = server_command(self.executable, self.model)
            self.info = {
                "backend": "llama.cpp", "schema_version": 2, "model": config.MODEL,
                "served_alias": config.ALIAS, "model_sha256": config.MODEL_SHA256,
                "model_path": str(self.model), "model_size": self.model.stat().st_size,
                "llamacpp_version": version_text, "executable_path": str(self.executable),
                "llamacpp_commit": "cd959bae9",
                "executable_sha256": runtime_hashes[self.executable.name], "runtime_files": runtime_hashes,
                "argv": command, "requested_context": config.CONTEXT_LENGTH, "requested_slots": 1,
                "sampling": {**config.SAMPLING, "samplers": config.SAMPLERS[:]},
                "gpu_layers_requested": 99, "kv_cache_types": {"k": "f16", "v": "f16"},
                "environment_policy": "isolated APPDATA/PROGRAMDATA; inherited LLAMA_* removed",
                "backend_started_at_utc": datetime.now(UTC).isoformat(),
            }
            dll = windows_job.kernel32()
            self.job = windows_job.create_job()
            windows_job.checked(dll.SetHandleInformation(self.job, 1, 1))
            try:
                self.process = subprocess.Popen(
                    [sys.executable, str(Path(windows_job.__file__).resolve()), str(self.job), *command],
                    env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, close_fds=False, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            finally:
                windows_job.checked(dll.SetHandleInformation(self.job, 1, 0))
            self.reader = threading.Thread(target=self._read_log, daemon=True)
            self.reader.start()
            deadline = time.monotonic() + startup_seconds
            while True:
                self.check_alive()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("llama.cpp did not become ready within the startup limit")
                try:
                    health = request_json("/health", self.token, timeout=min(5, remaining))
                    if health.get("status") == "ok":
                        break
                except urllib.error.HTTPError as exc:
                    if exc.code != 503:
                        raise
                except urllib.error.URLError:
                    pass
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            properties = self.verify(deadline)
            offload = None
            while time.monotonic() < deadline:
                self.check_alive()
                log_path = self.run_dir / "llama-server.log"
                if log_path.exists():
                    offload = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log_path.read_text(encoding="utf-8"))
                if offload is not None:
                    break
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            if offload is None or int(offload[1]) <= 0 or int(offload[1]) != int(offload[2]):
                raise RuntimeError("Full GPU offload could not be verified; see llama-server.log")
            self.info.update({
                "allocated_context": config.CONTEXT_LENGTH, "total_slots": 1,
                "chat_template": properties["chat_template"], "template_sha256": config.TEMPLATE_SHA256,
                "effective_generation_settings": properties["default_generation_settings"],
                "gpu_layers_offloaded": int(offload[1]),
                "backend_ready_at_utc": datetime.now(UTC).isoformat(),
            })
            return self.info
        except BaseException:
            self.close()
            raise

    def _read_log(self) -> None:
        try:
            with (self.run_dir / "llama-server.log").open("x", encoding="utf-8", buffering=1) as log:
                for line in self.process.stdout:
                    log.write(line.decode("utf-8", errors="replace").replace(self.token, "<redacted>"))
        except OSError:
            self.log_failed.set()
        finally:
            if not self.closing:
                self.log_failed.set()

    def close(self) -> bool:
        self.closing = True
        ok = True
        if self.job is not None:
            dll = windows_job.kernel32()
            try:
                if self.process is not None and self.process.poll() is None:
                    self.process.kill()
                windows_job.checked(dll.TerminateJobObject(self.job, 1))
            except OSError:
                ok = False
            finally:
                windows_job.checked(dll.CloseHandle(self.job))
                self.job = None
        if self.process is not None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return False
        if self.reader is not None:
            self.reader.join(timeout=5)
            if self.reader.is_alive():
                return False
            self.reader = None
        if self.process is not None and self.process.stdout:
            self.process.stdout.close()
        for file in self.files:
            file.close()
        self.files.clear()
        self.info["backend_termination"] = "owned_job_terminated" if self.process is not None else "not_started"
        return ok
