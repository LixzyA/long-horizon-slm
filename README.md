# Project description
This project researches long horizon tasks on small language models. The active backend is llama.cpp with the existing Qwen3.5 4.2B Q4_K_M text GGUF and a 32,768-token context. Earlier Ollama runs remain historical records; changing inference engines creates a new experimental condition.

# Supervised Pi run

The Windows supervisor runs one Pi task inside a Docker container. It copies the selected workspace into a new run directory and mounts only that copy at `/workspace`. By default, the supervisor reads `task.prompt` from that copy and sends its contents directly to Pi. For the concise Sokoban variant, it reads the separate prompt and saves the selected text in the run copy. The supervisor also enforces the time limit and detects repeated failed calls. An absent, empty, or unreadable selected prompt stops preparation before Pi starts. The original workspace is not modified by the agent.

## Prerequisites

1. Start Docker Desktop with Linux containers.
2. Install the official Windows CUDA 12.4 llama.cpp build **b12110** (commit `cd959bae9`), including its CUDA runtime DLLs. The verified local installation is `C:\Tools\llama.cpp\b12110\llama-server.exe`. The supervisor starts and stops its own server; leave port `8081` free. Do not start a server manually.
3. Install Pi 1.4.0 at its normal user location.
4. From the project directory, prepare the environment and build the image:

   ```powershell
   uv sync
   uv run python src/build_image.py
   ```

The image build copies the installed Pi 1.4.0 packages into a temporary build directory and uses pinned Node and Python base images. It does not mount the Pi installation into the running container. Rebuild after changing the Docker files or Pi installation. Before launching a run, the supervisor resolves the image tag to an immutable image ID and uses that ID for the agent, gateway, and network probe. Rebuilding the tag cannot change the image selected for an already prepared run.

The experiment uses the Qwen3.5 text GGUF with required SHA-256 `a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50`. Ollama does not need to run. The supervisor hashes and protects the GGUF, executable, and sibling DLLs against writes/replacement during each run. It rejects different weights or a different runtime build.

## Command-line options

Start the supervisor with the default limit of 2,700 seconds (45 minutes):

```powershell
uv run src/supervisor.py --puzzle one-push --thinking high
```

| Option | Description |
| --- | --- |
| `--limit-seconds SECONDS` | Set the maximum task time in seconds. The value must be a positive, finite number. The default is `2700`. |
| `--backend BACKEND` | Select `llamacpp` (default), `openrouter`, or `huggingface`. |
| `--thinking MODE` | Set the Pi model mode to `high` or `off`. The default is `high`. |
| `--task TASK` | Select `sokoban` (default). This option remains available for existing commands. |
| `--puzzle ID` | Select a board ID from the files in `src/sokoban/`. The default is `baseline`. |
| `--sokoban-prompt VARIANT` | Select `standard` (default) or `concise` for a Sokoban run. |
| `--llama-server PATH` | Override the configured path to the pinned Windows CUDA server executable. |
| `--model-file PATH` | Override the configured path to the selected text GGUF. |
| `-h`, `--help` | Show the command-line help and exit. No task starts. |

The supervisor reads its default paths from the local, Git-ignored `config.toml`. Copy `config.example.toml` to `config.toml` and edit the two paths if needed. Explicit command-line paths override the file. Puzzle boards and budgets are stored in separate split files under `src/sokoban/`; each run records its selected definition separately. These budgets are pilot choices, and the puzzles are not a validated difficulty scale.

## Sokoban board splits

The board files contain 70 one-box boards: [training](src/sokoban/puzzles-train.json) has 30, [validation](src/sokoban/puzzles-validation.json) has 20, and [test](src/sokoban/puzzles-test.json) has 20. Each board also has a `split` field. The five earlier boards belong to `train`. The 65 new IDs are `train-01` through `train-25`, `validation-01` through `validation-20`, and `test-01` through `test-20`. For example:

```powershell
uv run src/supervisor.py --puzzle train-01 --thinking high
```

Each new board has a verified shortest solution of 10 to 32 actions. Its action limit is twice that length plus eight. On a shortest route, at least one wrong push can put the box in a non-goal corner. Undo restores the prior state, and the solution then fits within the action limit. The existing five boards keep their original action limits. These budgets and lengths are pilot choices, not a validated difficulty scale.

The board test compares floor layouts across splits under rotations, reflections, and translations. Each pair differs by at least five floor cells under that check. This check cannot rule out every semantic similarity between boards. Keep validation and test boards and their trajectories out of SFT training data. Use only the training file to prepare SFT data. The supervisor reads all three files so that it can select an evaluation board; the files are not an access control. The boards do not themselves provide trajectories or inject mistakes.

To run the concise Sokoban prompt without changing the standard prompt:

```powershell
uv run src/supervisor.py --puzzle detour --thinking high --sokoban-prompt concise
```

The concise prompt is `src/sokoban/concise.prompt`. It changes only the per-action instructions. Each Sokoban run saves the selected assignment with the action limit substituted in `workspace/task.prompt` and records the variant in `model.json`. The supervisor also adds its standard preamble before submission. The prompt requests shorter reasoning but does not enforce its length.

For example, set a 60-second task limit:

```powershell
uv run src/supervisor.py --thinking off --limit-seconds 60
```

The task timer starts when the supervisor submits the prompt to Pi. It excludes model loading, network verification, and Pi startup. Backend readiness has a 120-second limit; Pi readiness has a separate 60-second limit. Hashing and version verification precede backend readiness. After a task timeout, Pi gets up to five seconds to acknowledge abort. Shutdown and cleanup can add time after the task deadline.

## OpenRouter experiment

To run a board with DeepSeek V4.1 Flash 1017 through OpenRouter, set `OPENROUTER_API_KEY` in the supervisor process environment. Do not put the key in the workspace or command arguments. Rebuild the image after updating the Docker files. Then run:

```powershell
uv run python src/build_image.py
uv run src/supervisor.py --backend openrouter --puzzle detour --thinking high
```

The model ID is `deepseek/deepseek-v4.1-flash-1017`. The agent uses the same board, action limit, task prompt, and deadline. Pi uses a 1,048,576-token context and a 16,384-token response limit for this route. The gateway sends Pi's reasoning setting and uses OpenRouter's default provider selection and sampling. These conditions differ from the local model. The gateway holds the OpenRouter key; the agent receives only a separate gateway token. OpenRouter processes the task, tool outputs, and conversation, and its service can charge for inference. The custom Pi model entry has no pricing data, so its cost estimate is not a billing record. `model.json` records the hosted condition. The gateway checks the key at startup, but it cannot verify the remote model weights or context allocation.

## Hugging Face experiment

This route uses [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/index) and the model `deepseek-ai/DeepSeek-V4.1-Flash`. Add `HF_TOKEN` to the local Git-ignored `.env` file, or set it in the supervisor process environment. The token needs the Hugging Face permission to make calls to Inference Providers. A process environment value takes precedence. The supervisor reads only `HF_TOKEN` from `.env`, and the gateway receives the token without placing it in the agent container or command arguments.

After updating the Docker files, rebuild the image and start a board:

```powershell
uv run python src/build_image.py
uv run src/supervisor.py --backend huggingface --puzzle one-push --thinking high
```

The gateway checks token identity through Hugging Face at startup. That check does not verify inference permissions, credits, model availability, or tool support. The router uses its default provider selection. The agent requests `reasoning_effort` of `high` or `none`, but support and behavior depend on the selected provider. The Pi configuration uses a 1,048,576-token context and a 16,384-token response limit. The remote provider's actual context limit and model weights are not verified. The Pi cost field is not a billing record.

This model is distinct from the earlier OpenRouter `DeepSeek-V4.1-Flash-1017` condition. Hugging Face runs use `supervisor-runs/deepseek-huggingface/`; prior OpenRouter runs remain under `supervisor-runs/deepseek/`. No model request is made until a task starts.

## Internal option: `--job-bootstrap`

Do not pass `--job-bootstrap` in a normal command. The supervisor passes it to a child copy of itself, together with a Windows Job Object handle and the agent command. The child joins the Job Object before it starts the Docker client. This lets the supervisor stop the processes in that job if an abort does not complete. The handle is an internal value for that launch. It is not a user parameter.

Separate owned Windows jobs contain the Docker client and native backend process trees. The supervisor removes the agent container, terminates the owned backend job, stops the gateway, and removes the network on completion, interruption, or failure. If the supervisor or Docker crashes, check Docker for a remaining `long-horizon-` container. An occupied backend port causes preparation to fail without stopping its listener.

## Agent launch settings

The supervisor supplies these settings to Pi. They are not command-line options of `supervisor.py`:

| Setting | Current value | Purpose |
| --- | --- | --- |
| Provider/model | `llamacpp` / `Qwen3.5-custom-32k` | Use the protected text GGUF through the gateway. |
| Pi context window | `32768` | Verify exactly 32,768 tokens in the backend's single slot. |
| Thinking | `high` by default | Enable the embedded template's thinking mode; `off` disables it. High is an on/off mapping, not a separate reasoning budget. |
| Sampling | temperature 1, top-k 20, top-p 0.95, min-p 0, repeat penalty 1.0, presence penalty 1.5 | The gateway supplies these on every request and rejects agent overrides. |
| Pi mode | `rpc` | Send the prompt and abort through Pi's RPC interface. |
| Pi session directory | `workspace/.pi-sessions/` within the run record | Retain Pi session files for this run. |

The one-box Sokoban pilot is the default task. Its rules, environment, pushing example, and output instructions are in `sokoban_workspace/task.prompt`; the Sokoban workspace does not require `AGENTS.md`. The supervisor starts one game and owns its state. The `one-push`, `align`, `baseline`, `offset`, and `detour` puzzles have 8, 12, 24, 28, and 60 actions respectively; direction and undo attempts count even when blocked. `python3 src/play.py show` shows the labeled board, player, box and goal coordinates, remaining actions, and outcome. `python3 src/play.py history` shows the recorded action history. Neither command uses an action. The agent sends each move through `src/play.py`; the supervisor records it outside the agent's workspace and stops the agent and backend immediately when the selected action limit is reached. There is no reset command. The game does not detect deadlocks or inject errors. Edit the appropriate task prompt to change an assignment. The fixed model, context, sampler order, and related settings live in `src/llamacpp_config.py`, shared with the gateway.

The container has a read-only root filesystem, a writable temporary directory, and one writable host bind mount: the per-run workspace copy. Linux system files remain visible inside the container. It runs as a non-root user with capabilities dropped. When present, the copied `AGENTS.md` has its original Windows paths replaced with Linux instructions; its run-output rules remain. Links and Windows junctions in the source workspace are rejected before copying.

Each run copies its selected workspace, including any output folders. Changes to the copy are not merged back into the original workspace. The supervisor creates an empty `output/` in the run copy before starting the model. If the copied workspace already has `output/`, preparation stops without overwriting it.

Pi runs on a dedicated Docker internal network in isolated gateway mode. Preflight verifies that the agent cannot reach llama.cpp on port 8081 or the public internet directly, that backend management routes are blocked, and that private web destinations are blocked. Only the trusted gateway can reach the backend, using a distinct private API key. The agent gets a separate gateway token. The gateway accepts only the selected model and thinking mode. For llama.cpp, it injects the trusted sampling settings and verified server alias, and checks backend health, model properties, template, context, and sampling before each inference request. Backend requests ignore inherited HTTP proxies. Closing a client request cancels its upstream connection even while the backend is quiet. For Sokoban the gateway also relays authenticated game requests and checks that the game service works before the task starts. Isolation failure stops preparation before Pi receives the task.

The server runs with full GPU offload, f16 key/value caches, Jinja tool formatting, one slot, and no context shifting. The supervisor isolates both Windows llama.cpp configuration roots and clears inherited `LLAMA_*` variables, so user/system INI files and environment defaults cannot silently alter the experiment. Backend exit or configuration mismatch fails the run; there is no fallback. The numeric sampling settings match `custom_model/Modelfile`. Earlier llama.cpp runs used repetition penalty 1.15; the current 1.0 is a different sampling condition. Runtime defaults, template handling, and sampling implementation can also differ. Compare llama.cpp runs as a new backend condition.

Public HTTP and HTTPS research goes through the gateway on ports 80 and 443. The gateway resolves public domains using certificate-verified DNS over HTTPS at Cloudflare (`1.1.1.1`), rejects non-public addresses, and connects to the validated address. The domain names looked up for research are sent to that DNS service. Programs must honor `HTTP_PROXY` or `HTTPS_PROXY`; tools that ignore them cannot reach the internet directly. Public web access depends on network availability.

The Python function `supervise()` has these parameters. They are not command-line options:

| Parameter | Description |
| --- | --- |
| `command` | The agent launch command as a list of arguments. |
| `prompt` | The task text to send to Pi. |
| `limit_seconds` | The task deadline in seconds. |
| `run_dir` | The directory for the event and outcome records. |
| `grace_seconds` | The wait for abort acknowledgement and process cleanup. The default is `5`. |
| `startup_seconds` | The maximum wait for Pi's readiness response. The default is `60`. |
| `game` | Optional supervisor-owned Sokoban game. The supervisor watches its limit and service status. |
| `stop_at_limit` | Optional callback that immediately removes the agent container when the game reaches its limit. |
| `backend` | Optional owned llama.cpp server; unexpected exit during startup or execution fails the run. |

## Records and outcomes

The supervisor prints the record directory at startup. Local runs use `supervisor-runs/local/`, OpenRouter DeepSeek runs use `supervisor-runs/deepseek/`, and Hugging Face DeepSeek runs use `supervisor-runs/deepseek-huggingface/`. The `supervisor-runs/unclassified/` folder holds older records without enough model metadata. Successful preparation creates `events.jsonl`, `outcome.json`, `model.json`, and the copied `workspace/` under `supervisor-runs/`. Local llama.cpp runs also contain `llama-server.log`. Sokoban runs contain authoritative `game.json`, `puzzle.json`, and `sokoban_rules.py` outside `workspace/`; deleting or editing workspace files does not reset the game. The saved rules are the exact source used by the run. To display a saved state, run `uv run python <run-directory>/sokoban_rules.py --state <run-directory>/game.json show`.

`model.json` records `backend: llama.cpp`, schema version, protected GGUF/runtime hashes and paths, template, llama.cpp build/commit, launch arguments, requested and verified context/sampling, thinking mapping, GPU offload, startup timestamps, backend termination, and `container_image_id`. The seed is random (`-1`), so these records do not promise exact trajectory reproduction. The image ID identifies the build shared by the agent, gateway, and probe. Startup failure still records `outcome.json` and any available backend information; `verification_complete` states whether backend verification finished. Historical Ollama records and Modelfiles are retained with their original meaning.

Pi session files use `workspace/.pi-sessions/`. `events.jsonl` retains completed messages, tool calls/results, and lifecycle events, excluding streaming update fragments. An interrupted response can lack a completed message. Non-JSON launcher output is printed but not retained in this event log. Terminal output and records can contain private information; backend API keys are excluded from retained arguments, logs, and metadata.

`outcome.json` records the limit, timestamps, elapsed task time when available, status, termination method, and launcher exit code. The status can be:

- `settled`: Pi stopped its run. This status does not prove task success.
- `timeout`: the task deadline expired. The termination value identifies a graceful abort acknowledgement or forced termination.
- `loop_detected`: ten consecutive calls to the same tool with identical arguments failed. `loop_detection` records the tool name, triggering call ID, and failure count. The supervisor requests an abort and uses forced termination if needed.
- `action_limit`: the Sokoban game recorded its final allowed action. The supervisor saves authoritative state, removes the agent container, and terminates its client and backend processes.
- `startup_error`: the supervisor did not submit the prompt. Invalid RPC records received before prompt submission are startup errors.
- `run_error`: the run ended unexpectedly after prompt submission, emitted an invalid RPC record, or Pi settled with an unrecovered model error. In the latter case, `error` preserves the model error message and `model_stop_reason` is `error`. A successful retry can still end as `settled`; the final assistant stop reason is recorded when available. RPC records must be JSON objects; other JSON values stop the run with a recorded error.
- `interrupted`: the user interrupted the supervisor with Ctrl+C.

The supervisor returns `0` for `settled` only when agent, backend, and gateway cleanup succeed; otherwise it returns `1`. Immediate action-limit cleanup failures are recorded as `immediate_container_stop` or `immediate_backend_stop`, and final cleanup retries are attempted. Final failures appear as `container_cleanup`, `backend_cleanup`, or `gateway_cleanup`: check for remaining experiment processes, containers, and networks. The owned native job is forcibly terminated during cleanup; `backend_termination` records that method. Forced termination can leave partial agent output files.

For Sokoban, `outcome.json` also records the authoritative game outcome, number of actions, and limit in its `game` field. Every shutdown waits for an action already being saved and freezes the game before recording that summary; later requests cannot change the final state. If that pending action reaches the selected action limit, the supervisor records `action_limit` and immediately stops the container. A solution on the final allowed action is recorded as `solved` even though the supervisor status is `action_limit`. Immediate termination can prevent the final action response or the agent's report from being delivered; use the authoritative `game.json` to inspect the final state. `settled` does not mean the puzzle was solved. A timeout can also interrupt the agent before it writes its report.

The loop detector counts only tool results that Pi marks as errors. A successful call or a different tool call resets the count. The supervisor does not enforce the agent's output directory within the copy. It is non-interactive. To steer or resume a session, use Pi separately after the supervisor exits.

## Sokoban replay viewer

Open `src/run_viewer/index.html` in a browser. Choose a run folder, or choose `game.json` together with its `puzzle.json` or saved Sokoban rules file. For older runs, select `workspace/src/sokoban.py` with the game file. The viewer reads files locally, replays actions, and warns when the reconstructed state differs from the saved state. Use the timeline or playback controls to inspect each step. Profile tasks do not contain a Sokoban board and cannot be replayed by this viewer.

## Tests

Run the ordinary unit and stand-in process suite with:

```powershell
uv run pytest
```

Real CUDA/Docker integration is opt-in, after rebuilding the image:

```powershell
$env:RUN_LLAMACPP_DOCKER_TEST = '1'
$env:RUN_SOKOBAN_DOCKER_TEST = '1'
$env:LLAMACPP_SERVER_EXE = 'C:\Tools\llama.cpp\b12110\llama-server.exe'
$env:LLAMACPP_MODEL_FILE = 'C:\Models\Qwen3.5-4B\qwen3.5-4b-q4_k_m.gguf'
uv run pytest -q tests/test_llamacpp_docker.py tests/test_sokoban_docker.py
```

These checks exercise real Pi tool calls in both thinking modes, stream cancellation, hostile external configuration, network isolation, and authoritative shutdown at the selected action limit. They are integration checks, not model task-performance trials.
