import hashlib
import io
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import llamacpp_config as config
import llamacpp_model


@pytest.fixture
def properties(monkeypatch: pytest.MonkeyPatch) -> dict:
    template = "test template"
    monkeypatch.setattr(config, "TEMPLATE_SHA256", hashlib.sha256(template.encode()).hexdigest())
    return {
        "total_slots": 1, "model_path": "C:/model.gguf", "chat_template": template,
        "default_generation_settings": {"n_ctx": 32768, "params": {**config.SAMPLING, "samplers": config.SAMPLERS[:]}},
    }


def test_properties_verify_effective_model_and_sampling(properties: dict) -> None:
    assert config.validate_properties(properties, "c:\\model.gguf") == properties


@pytest.mark.parametrize("field,value", [("total_slots", 2), ("total_slots", True), ("model_path", "other.gguf"), ("chat_template", "wrong")])
def test_wrong_runtime_is_rejected(properties: dict, field: str, value: object) -> None:
    properties[field] = value
    with pytest.raises(RuntimeError):
        config.validate_properties(properties, "C:/model.gguf")


@pytest.mark.parametrize("field,value", [("temperature", 0.8), ("top_p", None), ("samplers", [])])
def test_wrong_sampling_is_rejected(properties: dict, field: str, value: object) -> None:
    properties["default_generation_settings"]["params"][field] = value
    with pytest.raises(RuntimeError):
        config.validate_properties(properties, "C:/model.gguf")


def test_input_handles_deny_modification_and_replacement(tmp_path: Path) -> None:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"model")
    with llamacpp_model.locked_file(path) as file:
        assert file.read() == b"model"
        with pytest.raises(PermissionError):
            path.write_bytes(b"changed")
        with pytest.raises(PermissionError):
            path.unlink()
    path.write_bytes(b"released")


def test_child_environment_ignores_inherited_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_ARG_API_KEY_FILE", "old-key.txt")
    monkeypatch.setenv("LLAMA_ARG_AGENT", "1")
    monkeypatch.setenv("APPDATA", "old-user-config")
    monkeypatch.setenv("PROGRAMDATA", "old-machine-config")
    env = llamacpp_model.server_environment(tmp_path, "fresh-key")
    assert {k: v for k, v in env.items() if k.upper().startswith("LLAMA_")} == {"LLAMA_API_KEY": "fresh-key"}
    assert Path(env["APPDATA"]).is_dir() and Path(env["PROGRAMDATA"]).is_dir()
    assert env["APPDATA"] != env["PROGRAMDATA"]
    assert not list(Path(env["APPDATA"]).iterdir())
    assert env["SYSTEMROOT"]


def test_launch_contract_has_fixed_context_and_no_credentials() -> None:
    args = llamacpp_model.server_command(Path("server.exe"), Path("model.gguf"))
    assert args[args.index("--ctx-size") + 1] == "32768"
    assert args[args.index("--parallel") + 1] == "1"
    assert "--api-key" not in args
    assert args[args.index("--samplers") + 1] == ";".join(config.SAMPLERS)


def test_wrong_model_fails_without_starting_a_process(tmp_path: Path) -> None:
    executable, model = tmp_path / "server.exe", tmp_path / "wrong.gguf"
    executable.write_bytes(b"runtime")
    model.write_bytes(b"wrong model")
    server = llamacpp_model.LlamaServer(executable, model, tmp_path)
    with pytest.raises(RuntimeError, match="GGUF hash"):
        server.start()
    assert server.process is None and not server.files
    model.write_bytes(b"handles released")


def test_occupied_port_does_not_attach_or_stop_listener(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"file")
    server = llamacpp_model.LlamaServer(path, path, tmp_path)
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", config.PORT))
        listener.listen()
        with pytest.raises(OSError):
            server.start()
        assert listener.getsockname()[1] == config.PORT
    assert server.process is None and not server.files


def test_version_timeout_releases_verified_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable, model = tmp_path / "server.exe", tmp_path / "model.gguf"
    executable.write_bytes(b"runtime")
    model.write_bytes(b"model")
    monkeypatch.setattr(config, "MODEL_SHA256", hashlib.sha256(b"model").hexdigest())

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 15)

    monkeypatch.setattr(llamacpp_model.subprocess, "run", timeout)
    server = llamacpp_model.LlamaServer(executable, model, tmp_path)
    with pytest.raises(subprocess.TimeoutExpired):
        server.start()
    assert not server.files
    executable.write_bytes(b"released")


@pytest.mark.parametrize("code", ["import time; time.sleep(60)", "raise SystemExit(2)"])
def test_startup_failure_stops_owned_process_and_releases_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    executable, model = tmp_path / "server.exe", tmp_path / "model.gguf"
    executable.write_bytes(b"runtime")
    model.write_bytes(b"model")
    monkeypatch.setattr(config, "MODEL_SHA256", hashlib.sha256(b"model").hexdigest())
    monkeypatch.setattr(llamacpp_model.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "build 12110 commit cd959bae9", ""))
    monkeypatch.setattr(llamacpp_model, "server_command", lambda *a: [sys.executable, "-c", code])
    server = llamacpp_model.LlamaServer(executable, model, tmp_path)
    with pytest.raises(RuntimeError):
        server.start(startup_seconds=0.5)
    assert server.process.poll() is not None
    assert not server.files and server.job is None
    model.write_bytes(b"released")


def test_backend_logs_redact_the_private_token(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"file")
    server = llamacpp_model.LlamaServer(path, path, tmp_path)
    server.process = SimpleNamespace(stdout=io.BytesIO(("key=" + server.token + "\n").encode()))
    server.closing = True
    server._read_log()
    log = (tmp_path / "llama-server.log").read_text()
    assert server.token not in log and "<redacted>" in log


@pytest.mark.parametrize("models", [[{"id": config.ALIAS}, None], [None], [], [{"id": "other"}]])
def test_models_rejects_extra_and_malformed_entries(models: list) -> None:
    with pytest.raises(RuntimeError):
        config.validate_models({"data": models})


def test_readiness_requests_share_the_startup_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, properties: dict) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"file")
    server = llamacpp_model.LlamaServer(path, path, tmp_path)
    monkeypatch.setattr(server, "check_alive", lambda: None)
    monkeypatch.setattr(server, "model", Path("C:/model.gguf"))
    clock = iter([9.5, 10.1])
    monkeypatch.setattr(llamacpp_model.time, "monotonic", lambda: next(clock))
    calls = []

    def request(endpoint, token, timeout):
        calls.append((endpoint, timeout))
        return properties

    monkeypatch.setattr(llamacpp_model, "request_json", request)
    with pytest.raises(RuntimeError, match="deadline"):
        server.verify(deadline=10)
    assert calls == [("/props", 0.5)]
