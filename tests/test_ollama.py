import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ollama_model


def fake_responses(monkeypatch: pytest.MonkeyPatch, context: int) -> None:
    def open_url(request: object, timeout: int):
        url = request.full_url if hasattr(request, "full_url") else request
        if url.endswith("/api/show"):
            value = {
                "capabilities": ["tools", "thinking"],
                "parameters": "temperature 1\nrepeat_penalty 1.15",
            }
        elif url.endswith("/api/tags"):
            value = {
                "models": [{"name": "qwen-custom:latest", "digest": "model-digest"}]
            }
        elif url.endswith("/api/generate"):
            value = {"model": "qwen-custom", "done_reason": "load"}
        elif url.endswith("/api/ps"):
            value = {
                "models": [
                    {
                        "name": "qwen-custom:latest",
                        "digest": "model-digest",
                        "context_length": context,
                    }
                ]
            }
        else:
            raise AssertionError(url)
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(ollama_model.urllib.request, "urlopen", open_url)


def test_preflight_verifies_allocated_context_and_records_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_responses(monkeypatch, 131072)
    info = ollama_model.prepare_model("qwen-custom", 128000)
    assert info["model_digest"] == "model-digest"
    assert info["allocated_context"] == 131072
    assert "temperature 1" in info["parameters"]


def test_preflight_rejects_a_smaller_allocated_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_responses(monkeypatch, 4096)
    with pytest.raises(RuntimeError, match="context"):
        ollama_model.prepare_model("qwen-custom", 128000)
