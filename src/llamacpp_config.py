"""Fixed experiment contract shared by the host and trusted gateway."""

import hashlib
import math

MODEL = "Qwen3.5-custom-32k"
MODEL_SHA256 = "a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50"
TEMPLATE_SHA256 = "a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715"
ALIAS = "experiment-" + MODEL_SHA256
CONTEXT_LENGTH = 32768
PORT = 8081
SAMPLERS = ["penalties", "top_k", "top_p", "min_p", "temperature"]
SAMPLING = {
    "temperature": 1.0, "top_k": 20, "top_p": 0.95, "min_p": 0.0,
    "repeat_penalty": 1.0, "presence_penalty": 1.5, "frequency_penalty": 0.0,
    "repeat_last_n": 64, "seed": -1,
}


def validate_models(response: object) -> None:
    models = response.get("data") if isinstance(response, dict) else None
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict) or models[0].get("id") != ALIAS:
        raise RuntimeError("llama.cpp served model identity changed")


def validate_properties(properties: object, model_path: str) -> dict:
    if not isinstance(properties, dict):
        raise RuntimeError("Invalid llama.cpp properties")
    settings = properties.get("default_generation_settings", {})
    if not isinstance(settings, dict):
        raise RuntimeError("Invalid llama.cpp generation settings")
    params = settings.get("params", {})
    if type(properties.get("total_slots")) is not int or properties["total_slots"] != 1:
        raise RuntimeError("llama.cpp must have exactly one slot")
    if type(settings.get("n_ctx")) is not int or settings["n_ctx"] != CONTEXT_LENGTH:
        raise RuntimeError("llama.cpp context must be exactly 32768")
    actual_path = properties.get("model_path")
    if not isinstance(actual_path, str) or actual_path.replace("\\", "/").casefold() != model_path.replace("\\", "/").casefold():
        raise RuntimeError("llama.cpp model path changed")
    template = properties.get("chat_template")
    if not isinstance(template, str) or hashlib.sha256(template.encode()).hexdigest() != TEMPLATE_SHA256:
        raise RuntimeError("llama.cpp chat template changed")
    if not isinstance(params, dict) or params.get("samplers") != SAMPLERS:
        raise RuntimeError("llama.cpp sampler order changed")
    for name, expected in SAMPLING.items():
        actual = params.get(name)
        if name == "seed" and actual == 4294967295:
            actual = -1
        if type(actual) not in (int, float) or not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6):
            raise RuntimeError(f"llama.cpp sampling setting changed: {name}")
    return properties
