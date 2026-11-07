# Specification: migrate experiment inference to llama.cpp

Status: Independently reviewed and authorized; implementation and acceptance checks are recorded below. Requirements define the experiment contract; the verification record describes the checks actually run.

## Objective and scope

Replace Ollama with a local Windows `llama-server` for the existing Pi experiment. Keep the profile task, Sokoban task, Docker isolation, Pi 1.4.0 RPC interface, 32,768-token context, time limits, event records, and authoritative 24-action Sokoban game. This is one inference-backend migration, not a general provider framework.

The user approved reuse of the current model and sampling settings and supervisor-managed server ownership: one host server per experiment, launched and stopped by the supervisor. Manually managed servers and simultaneous experiments are outside scope.

Success means a real Pi tool-call round trip works through the protected gateway with this model, both thinking modes work, and all existing game and shutdown guarantees remain intact. A successful ordinary chat response alone is insufficient.

## Verified starting point

Read from the running Ollama instance and local model headers on 2026-11-07:

| Item | Current value |
| --- | --- |
| Model alias | `Qwen3.5-custom-32k:latest` |
| Model | Qwen3.5 4.2B, Q4_K_M, GGUF architecture `qwen35` |
| Ollama manifest digest | `6ff7420c172cec32846d101a2a04773a3d2b6439f46570f23e16a300ea7628ec` |
| Text-model blob | `C:\Users\felix\.ollama\models\blobs\sha256-a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50` |
| Verified text-model SHA-256 | `a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50`; independently computed from file bytes; recompute before each run |
| Text-model size | 2,648,593,216 bytes |
| Embedded chat-template SHA-256 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |
| Hardware observed | NVIDIA RTX 3060 Laptop GPU, 6,144 MiB VRAM; driver 610.88 |

The second Ollama blob (`e56a899b...`) is a CLIP vision projector. These experiments use text only, so the migration uses the text GGUF without the projector. Vision support is outside scope. Do not confuse the Ollama manifest digest with the GGUF file hash.

The GGUF contains a 7,756-character Jinja chat template with `enable_thinking`. Ollama currently uses its own `qwen3.5` renderer/parser and reports `TEMPLATE {{ .Prompt }}`. That Ollama template is not a replacement for the embedded GGUF template.

The implementation uses the official Windows CUDA 12.4 build **b12110**, commit `cd959bae99ff4bed22bef2604f45241c09bbb8c8`. It reports `version: 0.9.0-dev (build 12110, commit cd959bae9)`. The installed executable is `C:\Tools\llama.cpp\b12110\llama-server.exe`, with its sibling runtime DLLs. No model download or conversion was needed.

The official release archives were downloaded with normal Windows certificate verification and their published SHA-256 values checked before extraction:

| [Official b12110 release](https://github.com/ggml-org/llama.cpp/releases/tag/b12110) asset | SHA-256 |
| --- | --- |
| `llama-b12110-bin-win-cuda-12.4-x64.zip` | `1ce755bc3a061889234048f88e33328e17971eaad73c4666cfeb26026b317fee` |
| `cudart-llama-bin-win-cuda-12.4-x64.zip` | `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6` |

Runtime files and model bytes stay outside version control. The small executable loads `llama-server-impl.dll`; protect and hash all sibling DLLs as well as the executable and GGUF during each run.

## Tech stack and configuration

- Python 3.12, standard library, `uv`, and pytest; no new Python dependency.
- Existing pinned Docker image and Windows Job Object process control.
- One Windows CUDA `llama-server`, single model and single slot. No router, model autoloading, speculative model, or fallback to Ollama.
- New supervisor arguments: `--llama-server PATH` and `--model-file PATH`. Both identify existing local files. Preserve `--task`, `--thinking`, and `--limit-seconds`.
- Fixed initial backend port: `8081`. An occupied port is a preparation error; do not attach to, replace, or terminate an existing listener.
- Backend paths and executable/model hashes are recorded, but model bytes and runtime binaries are never committed or copied into the agent workspace.

## Commands

Current development commands remain executable:

```powershell
uv sync
uv run pytest
uv run python src/build_image.py
```

Commands for the verified local installation:

```powershell
uv run src/supervisor.py --task sokoban --thinking high `
  --llama-server 'C:\Tools\llama.cpp\b12110\llama-server.exe' `
  --model-file "$env:USERPROFILE\.ollama\models\blobs\sha256-a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50"

uv run src/supervisor.py --task profile --thinking off --limit-seconds 60 `
  --llama-server 'C:\Tools\llama.cpp\b12110\llama-server.exe' `
  --model-file "$env:USERPROFILE\.ollama\models\blobs\sha256-a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50"
```

Opt-in integration verification:

```powershell
$env:RUN_LLAMACPP_DOCKER_TEST = '1'
$env:RUN_SOKOBAN_DOCKER_TEST = '1'
$env:LLAMACPP_SERVER_EXE = 'C:\Tools\llama.cpp\b12110\llama-server.exe'
$env:LLAMACPP_MODEL_FILE = "$env:USERPROFILE\.ollama\models\blobs\sha256-a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50"
uv run pytest -q tests/test_llamacpp_docker.py tests/test_sokoban_docker.py
```

There is no configured project lint/type-check command; do not invent one or add tooling for this migration.

## Backend launch and identity contract

1. Validate the executable and GGUF before starting the agent. Record `llama-server --version`, its SHA-256, GGUF SHA-256/size, resolved paths, embedded template/hash, and the intended launch arguments. Verify the GGUF hash against the selected model. Fail clearly if it differs; do not silently select another blob or model.
2. Bind identity to the bytes actually loaded: retain Windows read handles denying writes/replacement while hashing and using the selected GGUF and executable, or demonstrate an equally strong immutable-input mechanism. Do not claim that a model alias or `/v1/models` proves the loaded GGUF hash.
3. Launch one owned server hidden on Windows, using an argument list rather than shell interpolation. Use the existing Job Object pattern to stop its descendants if the supervisor exits. Retain server stdout/stderr outside the agent workspace and drain them without blocking the process. Every invocation, including `--version`, uses a child-only controlled environment: remove inherited `LLAMA_*` settings, redirect both `APPDATA` and `PROGRAMDATA` to newly created supervisor-owned empty configuration roots outside the agent workspace, preserve required Windows/CUDA variables, and inject only the run's fresh `LLAMA_API_KEY` as a llama.cpp override. The pinned parser automatically reads INI configuration from both roots and has no `--no-config` switch. Do not modify real user/system configuration. Cache paths are separate from these configuration roots and must be explicit if overridden. Record the non-secret environment policy. This prevents inherited API keys, adapters, cache precision, built-in host tools, MCP, router settings, or tunnels from changing the launch contract.
4. The launch contract is equivalent to the following flags, with runtime paths supplied by the supervisor:

   ```text
   --model <verified-gguf> --alias experiment-<full-gguf-sha256>
   --host 0.0.0.0 --port 8081 --ctx-size 32768 --parallel 1
   --jinja --reasoning-format deepseek --no-context-shift
   --n-predict 16384 --n-gpu-layers 99
   --cache-type-k f16 --cache-type-v f16 --no-agent --no-ui-mcp-proxy
   --verbosity 4 --log-colors off --offline
   --temp 1 --top-k 20 --top-p 0.95 --min-p 0
   --repeat-penalty 1.15 --presence-penalty 1.5
   --frequency-penalty 0 --repeat-last-n 64 --seed -1
   --samplers penalties;top_k;top_p;min_p;temperature
   ```

   `99` requests full offload; the verified runtime offloads all 33/33 layers with the specified 32,768-token context and f16 caches on this GPU. Startup checks the retained offload log; verbosity 4 is required because the default level omits that evidence. A memory or context failure must not silently reduce context, quantize caches, or change sampling. An explicit offload adjustment requires documenting and recording the revised launch configuration before running the experiment.
5. Generate a distinct per-run backend API key and pass it through `LLAMA_API_KEY` to the server. Give it only to the supervisor and trusted gateway. The agent receives only its existing gateway token. Keys must not appear in retained launch arguments, server logs, prompts, or metadata.
6. Allow up to 120 seconds for backend readiness, separate from hashing/version verification, Pi's existing 60-second startup period, and the task timer. Poll `/health`, then authenticated `/props` and `/v1/models` using one readiness deadline. Check owned-process liveness, expected alias/path, `total_slots == 1`, per-slot context exactly 32,768, template identity, and effective sampler values/order. Compare floats with relative/absolute tolerance `1e-6`. Normalize the server's unsigned seed value `4294967295` to the configured random-seed policy `-1`. Missing or incompatible properties are preparation errors.
7. `/props` does not supply a cryptographic identity guarantee. Identity comes from verified protected input files, the owned server process, a fresh secret, and cross-checking its reported properties. Monitor the owned process throughout readiness, Pi startup, execution, and shutdown. Unexpected exit stops the run; never reconnect automatically to a replacement process.

Relevant upstream contracts: [pinned server documentation](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/tools/server/README.md), [function calling](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/docs/function-calling.md). These document the endpoints, single-slot/context flags, Jinja tool support, and reasoning fields; live verification remains required.

Configuration precedence and Windows root lookups are verified against the pinned [argument parser](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/arg.cpp#L656) and [configuration-directory lookup](https://github.com/ggml-org/llama.cpp/blob/cd959bae99ff4bed22bef2604f45241c09bbb8c8/common/common.cpp#L962).

## Pi and gateway contract

- Keep Pi's `openai-completions` API and gateway URL `http://gateway:8080/v1`. Rename the local provider from `ollama` to `llamacpp`; the existing logical model ID can remain `Qwen3.5-custom-32k` to limit unnecessary changes. Record `backend: llama.cpp` so the logical ID is not mistaken for an Ollama experiment.
- Preserve Pi's context window 32,768, maximum output 16,384, RPC/session settings, and compaction behavior. Preserve the existing OpenAI compatibility options unless a live compatibility test proves a change is needed.
- Accept only the fixed logical model ID from the agent, then replace it with the server's verified `experiment-<sha256>` alias. A llama.cpp alias is a selector/display name, not an equivalent of Ollama digest addressing.
- Forward only authenticated `POST /v1/chat/completions` and the existing supervisor-owned Sokoban endpoint. Keep the current request-field allowlist and prohibit caller-supplied sampling values, backend URLs, model paths, templates, adapters, grammars, and router controls.
- The trusted gateway sets the recorded sampling values/order explicitly on every upstream completion, using the pinned server's supported fields. This prevents OpenAI-route defaults from changing the effective experiment settings. Preserve the six numeric settings observed in Ollama: temperature 1, top-k 20, top-p 0.95, min-p 0, repeat penalty 1.15, and presence penalty 1.5. The explicitly chosen repetition window, sampler order, and other disabled settings are part of the new backend condition, not proven identical Ollama behavior.
- `--thinking high` retains Pi's high setting and translates to thinking enabled (`chat_template_kwargs.enable_thinking = true`). `off` translates to false and `reasoning_effort = none`. Reject conflicting caller settings. For this Qwen template, high means enabled thinking; do not claim a distinct high-effort budget unless the template actually implements one.
- Parse reasoning into `reasoning_content` and prove that Pi retains it as thinking, while structured `tool_calls`, call IDs, arguments, tool results, finish reasons, usage, and streaming boundaries remain usable. Prefer native compatibility; introduce no stream adapter unless a demonstrated mismatch requires one.
- The gateway uses authenticated `/health`/`/props` checks before inference instead of Ollama `/api/generate` and `/api/ps`. It must reject a mismatched alias, context, template, or sampler configuration rather than forwarding. Health alone does not verify model identity.
- Change host routing to `host.docker.internal:8081`, and update all verification probes to the actual backend port. The agent must fail direct connections to it. The trusted gateway must reach it. The existing public-web proxy must continue rejecting private destinations, including this backend.
- Do not enable the server's mutable properties mode, router/model loading, or adapter-management facilities. The agent cannot access `/props`, `/slots`, `/completion`, `/models/load`, `/models/unload`, or other backend routes through the gateway. Ollama port 11434 is no longer an active experiment dependency.

## Lifetime, failures, and records

- Own backend preparation and cleanup within the supervisor's existing run lifetime. Setup/probes finish before the prompt starts the task clock. No backend launch failure may start an agent or consume a game action.
- At action 24, save authoritative state first and immediately stop the agent as today. Also cancel/stop the owned backend so inference cannot continue after the experiment ends. A solution on action 24 still records game outcome `solved` and supervisor status `action_limit`.
- Preserve freeze-before-summary behavior, pending-save synchronization, save-failure reporting, model-error classification, RPC validation, timeouts, loop detection, and Ctrl+C handling. Cleanup must run even if loading, readiness, gateway startup, or Pi startup fails. Never terminate an unrelated listener or an externally started server.
- Retain bounded startup/readiness/cleanup waits. Request cancellation closes the upstream connection even during prompt processing or a quiet stream. Owned native servers are stopped with Windows Job Object termination; there is no authenticated cooperative shutdown endpoint in this runtime contract. First terminate the specific owned bootstrap to prevent it joining an already-terminated empty job. Cleanup failures must be visible in the run record.
- Keep `game.json`, `sokoban_rules.py`, `events.jsonl`, `outcome.json`, and the exact container image ID. Add retained `llama-server.log` outside the writable workspace. Preserve historical Ollama records without rewriting their fields.
- New `model.json` records `backend`, record schema version, logical ID, served alias, model SHA-256/size/path, template/hash, llama.cpp version/build/commit when reported, executable SHA-256/path, redacted argv, requested/effective context and slot count, requested/effective sampling chain and values, thinking mapping, GPU/offload configuration, startup timestamps, and container image ID. `seed=-1` records a random-seed policy, not exact trajectory reproducibility. Do not reuse `ollama_version` or an Ollama manifest digest to label llama.cpp artifacts.
- Backend startup/runtime/cleanup failures need an explicit recorded reason. A provider error followed by `agent_settled` remains `run_error` unless a later successful retry recovers. No silent fallback to Ollama, CPU-only execution, different weights, or a smaller context.

## Project structure and affected interfaces

| Location | Responsibility in the migration |
| --- | --- |
| `src/llamacpp_model.py` | Concrete server launch, protected file identity, authenticated preflight, metadata, and cleanup; reuse current HTTP/error patterns |
| `src/llamacpp_config.py`, `src/windows_job.py` | Shared fixed backend contract and existing Windows process-control primitives |
| `src/supervisor.py` | New path arguments, backend lifecycle/monitoring, unchanged task supervision |
| `src/network_guard.py`, `src/container_run.py` | Backend port/credential wiring and image-pinned probes/containers |
| `docker/gateway.py`, `docker/entrypoint.sh` | Controlled llama.cpp requests and Pi provider configuration |
| `tests/test_llamacpp.py`, `tests/test_llamacpp_docker.py` | Backend unit/failure tests and opt-in integration |
| Existing gateway, supervisor, network, container, and Sokoban tests | Preserve all affected behavior and callers |
| `README.md` | Replace active Ollama setup/launch instructions with verified llama.cpp commands |

Remove `src/ollama_model.py` and replace its active tests once all runtime callers migrate; keep historical Modelfiles as experiment provenance with their purpose documented. Do not keep a dormant backend-selection abstraction. Task prompts, board mechanics, and action budgets need no experimental changes.

## Code style

Use four-space indentation, `snake_case`, `PascalCase` for classes, annotations on public interfaces, and standard-library argument-list subprocess calls. Keep runtime files outside the agent workspace.

Illustrative style only:

```python
def validate_context(properties: dict, expected_context: int) -> None:
    actual = properties.get("default_generation_settings", {}).get("n_ctx")
    if type(actual) is not int or actual != expected_context:
        raise RuntimeError(f"Backend context {actual!r}; expected {expected_context}.")
```

## Testing strategy and success criteria

Use pytest under `tests/`. Keep ordinary tests independent of installed model binaries. Use mock HTTP responses and the existing stand-in process approach for lifecycle failures. Do not install new test dependencies or weaken existing assertions.

Acceptance requires:

1. Unit tests reject wrong/missing model files, wrong hashes, unsupported metadata, occupied ports, bad authentication, loading timeout, slot/context mismatch, and sampler/template mismatch. Assert model and binary protection spans hashing/loading, and credentials are redacted. Use temporary hostile user/system INI files and inherited `LLAMA_*` values to verify child environment isolation without changing actual host configuration. Include a real integration case with `cache-type-k=q8_0` and a known old API key in the caller's temporary config: the new server must keep the specified f16 cache configuration, reject the old key, accept only its run key, and start no host tools/MCP/adapters. Both version and server invocations must ignore those external defaults.
2. Gateway tests cover both thinking translations, strict caller validation, explicit upstream sampling, alias rewriting, backend identity mismatch, streaming errors, and non-exposure of backend management endpoints.
3. A real Pi-to-gateway-to-llama-server test performs a structured tool call, executes a harmless tool, returns its result, and obtains the next assistant response. Test thinking enabled and disabled, including reasoning/tool separation and error/finish-reason handling. A small standalone chat smoke does not replace this gate.
4. Docker verifies the direct backend path is blocked, the trusted gateway path works, private-address web proxy requests remain blocked, and all containers use the same recorded image ID.
5. Every shutdown path stops only the owned server. Test an unexpected backend exit while Pi is starting and running, caller cancellation, Ctrl+C, timeout, startup failure, and forced cleanup. Preserve final game/outcome consistency and the action-24 stop regression, including a final-action solution.
6. The same GGUF loads with verified 32,768 per-slot context on this machine. Record requested/effective offload and memory failures; do not promise a speed gain or silently change the experimental configuration to make it fit.
7. Full tests, rebuilt image, and opt-in integration pass before collecting a new Sokoban experiment. Retain the implementation's commands and actual verification results. No full experiment is part of the specification-writing step.

The engine, chat rendering, tool parsing, and sampling implementation can change behavior even with identical GGUF bytes and numeric settings. Treat llama.cpp runs as a new backend condition; do not pool them with Ollama runs or attribute changes solely to model ability.

## Boundaries

- Always: preserve both tasks and previous run data, validate identities/settings before inference, retain failure evidence, keep secrets out of records, run relevant tests before committing implementation, and obtain independent review.
- Ask first: change weights/quantization, context, game prompt/rules/budget, selected sampling values, add dependencies, change CI, or expand to externally managed/multiple backends. Supplying the already selected runtime/model file paths is ordinary configuration.
- Never: delete old experiments, stop a process the supervisor does not own, trust a model alias as a file hash, expose backend credentials to the agent, download/requantize models silently, weaken isolation, or record unverified settings as verified.

## Authorization and execution prerequisites

1. The user authorized implementation of this reviewed specification, including supervisor-managed server ownership and reuse of the exact selected text GGUF and sampling settings. No further approval gate is required before implementation within this scope.
2. The pinned Windows CUDA runtime has been installed and its build, archive hashes, full GPU offload, context, template, and effective samplers verified on this machine. Its path is ordinary configuration.
3. Real Pi tool-call round trips passed with thinking enabled and disabled, using the original embedded template and specified offload settings. No template/offload experimental-condition change was needed. Any future such change still requires documenting and approving the revised condition.

The specification review and implementation authorization are complete. The verification record below tracks the acceptance gates; implementation alone does not clear them.

## Implementation verification

Implementation date: 2026-11-07. The independent reviewer is GPT-6.1 Sol at xhigh, using Ponytail review. Its spec corrections were incorporated before implementation. Implementation review identified and corrected a bootstrap/job cleanup race, backend-exit status misclassification, quiet-upstream cancellation, inherited HTTP proxy exposure, and lost gateway cleanup ownership after a failed removal. The final review cleared all findings.

Real Pi tests run the bash tool, verify its returned output, receive the following assistant response, and check reasoning blocks in the retained trace for both thinking modes. The Docker game test exercises authoritative action counting and immediate agent/backend shutdown at action 24. These are integration checks, not Sokoban task-performance trials. Old task prompts, puzzle rules, and historical run artifacts remain unchanged.

| Gate | Actual result |
| --- | --- |
| Full pytest suite with both opt-in environment gates enabled | **140 passed**, 144.18 seconds, zero skips |
| Real Pi tool round trip | Passed with thinking `off` and `high`; returned `LLAMACPP_TOOL_OK`, followed by `INTEGRATION_OK` |
| Backend context/offload/template/sampling | Verified 32,768 tokens, one slot, all 33/33 layers on GPU, original template and selected settings |
| External configuration isolation | Temporary user/system INI files and inherited overrides ignored; old API key rejected; run key accepted; f16 caches verified |
| Cancellation | Live single-slot release passed; quiet upstream tested before and after response headers |
| Shutdown/failures | Backend exit, startup failure, timeouts, Ctrl+C, cleanup failures/retries, and action 24 covered |
| Rebuilt image | `sha256:d8448588b1ada783951982b0a5218d25f844dd4ee30d3ae40f10d613f837f204` |

Retained acceptance report: `supervisor-runs/llamacpp-acceptance-cbf68211/pytest-normal-temp.xml`; selected live traces/logs are copied to that directory's `normal-temp-traces/`. Protected model/runtime preflight metadata is in `supervisor-runs/llamacpp-preflight-0d4660f6/model.json`. These local artifacts are ignored by Git.

A preceding run with pytest temporary files inside the repository encountered two Windows `WinError 5` atomic-save failures in existing game tests. The passing full suite used pytest's normal temporary directory; those failures were not suppressed or converted to passes. No full gameplay experiment or speed comparison was run.
