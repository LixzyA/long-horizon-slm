import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ollama_model


def fake_responses(monkeypatch: pytest.MonkeyPatch, context: int) -> list:
    calls = []
    def open_url(request: object, timeout: int):
        url = request.full_url if hasattr(request, "full_url") else request
        calls.append((url.rsplit("/", 1)[-1], json.loads(request.data) if request.data else None))
        if url.endswith("/api/show"):
            value = {
                "capabilities": ["tools", "thinking"],
                "parameters": "temperature 1\nrepeat_penalty 1.15",
            }
        elif url.endswith("/api/tags"):
            value = {
                "models": [{"name": "Qwen3.5-custom-32k:latest", "digest": "model-digest"}]
            }
        elif url.endswith("/api/generate"):
            value = {"model": "Qwen3.5-custom-32k", "done_reason": "load"}
        elif url.endswith("/api/ps"):
            value = {
                "models": [
                    {
                        "name": "another-alias:latest",
                        "digest": "model-digest",
                        "context_length": context,
                    }
                ]
            }
        else:
            raise AssertionError(url)
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(ollama_model.urllib.request, "urlopen", open_url)
    return calls


def test_preflight_verifies_allocated_context_and_records_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_responses(monkeypatch, 32768)
    info = ollama_model.prepare_model("Qwen3.5-custom-32k", 32768)
    assert info["model_digest"] == "model-digest"
    assert info["allocated_context"] == 32768
    assert "temperature 1" in info["parameters"]
    assert next(payload for endpoint, payload in calls if endpoint == "show") == {"model": "model-digest"}
    assert next(payload for endpoint, payload in calls if endpoint == "generate")["model"] == "model-digest"


@pytest.mark.parametrize("context", [32767, 32769])
def test_preflight_rejects_an_incorrect_allocated_context(
    monkeypatch: pytest.MonkeyPatch, context: int
) -> None:
    fake_responses(monkeypatch, context)
    with pytest.raises(RuntimeError, match="context"):
        ollama_model.prepare_model("Qwen3.5-custom-32k", 32768)
