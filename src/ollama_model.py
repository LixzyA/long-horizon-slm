import json
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:11434"


def request_json(
    path: str, payload: dict[str, Any] | None = None, timeout: int = 10
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RuntimeError(f"Ollama request failed for {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise TypeError(f"Ollama returned an invalid response for {path}.")
    return result


def prepare_model(model: str, expected_context: int) -> dict[str, Any]:
    version = request_json("/api/version").get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Cannot identify the Ollama version.")
    names = {model, model + ":latest"}
    tags = request_json("/api/tags").get("models", [])
    matches = [item for item in tags if item.get("name") in names]
    if len(matches) != 1 or not matches[0].get("digest"):
        raise RuntimeError("Cannot identify the selected model digest.")
    digest = matches[0]["digest"]
    details = request_json("/api/show", {"model": digest})
    if not {"tools", "thinking"}.issubset(details.get("capabilities", [])):
        raise RuntimeError("The Ollama model must support both tools and thinking.")
    request_json(
        "/api/generate",
        {"model": digest, "prompt": "", "stream": False, "keep_alive": "10m"},
        timeout=120,
    )
    running = request_json("/api/ps").get("models", [])
    active = [
        item
        for item in running
        if item.get("digest") == digest
    ]
    if len(active) != 1:
        raise RuntimeError("Cannot verify the loaded Ollama model identity.")
    context = active[0].get("context_length")
    if (
        not isinstance(context, int)
        or isinstance(context, bool)
        or context != expected_context
    ):
        raise RuntimeError(
            f"Ollama allocated context {context}; exactly {expected_context} is required."
        )
    return {
        "ollama_version": version,
        "model": model,
        "model_digest": digest,
        "parameters": details.get("parameters", ""),
        "allocated_context": context,
        "thinking": True,
    }
