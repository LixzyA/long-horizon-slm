import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import container_run
import network_guard
import supervisor
from llamacpp_model import LlamaServer

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LLAMACPP_DOCKER_TEST") != "1", reason="requires the pinned CUDA runtime and Docker")


def test_disconnecting_a_stream_releases_the_single_backend_slot(tmp_path: Path, llamacpp_backend) -> None:
    backend = llamacpp_backend
    name = "long-horizon-cancel-test-" + uuid.uuid4().hex
    token = container_run.new_token()
    image = network_guard.resolve_image(container_run.IMAGE)
    guard = network_guard.GatewaySession(name, token, str(backend.model), backend_token=backend.token, image=image)
    client = '''
import json, os, time, urllib.request
def request(limit):
    return urllib.request.Request("http://gateway:8080/v1/chat/completions", data=json.dumps({
        "model": "Qwen3.5-custom-32k", "reasoning_effort": "high", "stream": True,
        "max_tokens": limit, "messages": [{"role": "user", "content": "Count from 1 to 100000, one integer per line. Continue until 100000."}],
    }).encode(), headers={"Authorization": "Bearer " + os.environ["GATEWAY_TOKEN"], "Content-Type": "application/json"})
with urllib.request.urlopen(request(4096), timeout=30) as response:
    for line in response:
        if not line.startswith(b"data: {"):
            continue
        delta = json.loads(line[6:])["choices"][0]["delta"]
        if delta.get("content") or delta.get("reasoning_content"):
            break
    else:
        raise RuntimeError("No streamed token received")
started = time.monotonic()
with urllib.request.urlopen(request(1), timeout=30) as response:
    assert b"[DONE]" in response.read()
assert time.monotonic() - started < 25, "The cancelled request retained the only slot"
print("cancelled stream; next request completed")
'''
    try:
        guard.start()
        result = subprocess.run([
            "docker", "run", "--rm", "--network", guard.network,
            "--env", "GATEWAY_TOKEN=" + token, "--entrypoint", "python", image, "-c", client,
        ], capture_output=True, text=True, timeout=70)
        assert result.returncode == 0, result.stderr
        assert "next request completed" in result.stdout
    finally:
        assert guard.close()


@pytest.mark.parametrize("thinking", ["off", "high"])
def test_real_pi_completes_a_tool_round_trip(tmp_path: Path, llamacpp_backend, thinking: str) -> None:
    backend = llamacpp_backend
    run = tmp_path / "run"
    workspace = run / "workspace"
    workspace.mkdir(parents=True)
    token = container_run.new_token()
    name = "long-horizon-pi-test-" + uuid.uuid4().hex
    image = network_guard.resolve_image(container_run.IMAGE)
    guard = network_guard.GatewaySession(name, token, str(backend.model), thinking, backend_token=backend.token, image=image)
    try:
        guard.start()
        command = container_run.container_command(workspace, name, guard.network, token, thinking, image=image)
        result = supervisor.supervise(
            command,
            'This is a transport integration test. Use the bash tool to run exactly: python3 -c "print(\'LLAMACPP_TOOL_OK\')". '
            'After reading its output, reply INTEGRATION_OK. Do not create files or run other commands.',
            120, run, backend=backend,
        )
        assert result["status"] == "settled", result
        records = [json.loads(line) for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        completed = [i for i, r in enumerate(records) if r.get("type") == "tool_execution_end" and not r.get("isError") and "LLAMACPP_TOOL_OK" in json.dumps(r.get("result"))]
        assert completed, "No successful real tool execution"
        assert any(r.get("type") == "message_end" and r.get("message", {}).get("stopReason") == "stop" for r in records[completed[-1] + 1:])
        thoughts = [part for r in records if r.get("type") == "message_end" for part in r.get("message", {}).get("content", []) if isinstance(part, dict) and part.get("type") == "thinking" and part.get("thinking", "").strip()]
        assert bool(thoughts) == (thinking == "high")
    finally:
        assert container_run.cleanup_container(name)
        assert guard.close()


def test_server_ignores_hostile_machine_and_user_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("APPDATA", "PROGRAMDATA"):
        root = tmp_path / variable
        (root / "llama.cpp").mkdir(parents=True)
        (root / "llama.cpp" / "config.ini").write_text("api-key=known-old-key\ncache-type-k=q8_0\n", encoding="utf-8")
        monkeypatch.setenv(variable, str(root))
    old_keys = tmp_path / "keys.txt"
    old_keys.write_text("known-old-key\n", encoding="utf-8")
    monkeypatch.setenv("LLAMA_ARG_API_KEY_FILE", str(old_keys))
    monkeypatch.setenv("LLAMA_ARG_AGENT", "1")
    monkeypatch.setenv("LLAMA_ARG_CACHE_TYPE_K", "q8_0")
    from llamacpp_model import request_json
    import urllib.error

    run = tmp_path / "run"
    run.mkdir()
    backend = LlamaServer(Path(os.environ["LLAMACPP_SERVER_EXE"]), Path(os.environ["LLAMACPP_MODEL_FILE"]), run)
    try:
        backend.start()
        with pytest.raises(urllib.error.HTTPError) as failure:
            request_json("/props", "known-old-key")
        assert failure.value.code == 401
        assert request_json("/props", backend.token)["total_slots"] == 1
        log = (run / "llama-server.log").read_text(encoding="utf-8")
        assert "using config file:" not in log
        assert "K (f16):" in log and "V (f16):" in log
        assert backend.token not in log
    finally:
        assert backend.close()
