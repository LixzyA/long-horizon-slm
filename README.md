# Project description
This is a project for researching long horizon tasks on small language models. The first few experiment is run on Qwen3.5-0.8B-GGUF.

# Supervised Pi run

The Windows supervisor runs one Pi task inside a Docker container. It copies the selected workspace into a new run directory and mounts only that copy at `/workspace`. The supervisor reads `task.prompt` from that copy and sends its contents directly to Pi; it also enforces the time limit and detects repeated failed calls. An absent, empty, or unreadable `task.prompt` stops preparation before Pi starts. The original workspace is not modified by the agent.

## Prerequisites

1. Start Docker Desktop with Linux containers.
2. Start Ollama. Create the 32k model with `ollama create Qwen3.5-custom-32k -f ollama_model/Modelfile32k`. This uses the existing `Qwen3.5-custom` model. Check `ollama show Qwen3.5-custom-32k --parameters` for its saved settings.
3. Install Pi 1.4.0 at its normal user location.
4. From the project directory, prepare the environment and build the image:

   ```powershell
   uv sync
   uv run python src/build_image.py
   ```

The image build copies the installed Pi 1.4.0 packages into a temporary build directory and uses pinned Node and Python base images. It does not mount the Pi installation into the running container. Rebuild after changing the Docker files or Pi installation.

## Command-line options

Start the supervisor with the default limit of 2,700 seconds (45 minutes):

```powershell
uv run src/supervisor.py
```

| Option | Description |
| --- | --- |
| `--limit-seconds SECONDS` | Set the maximum task time in seconds. The value must be a positive, finite number. The default is `2700`. |
| `--thinking MODE` | Set the Pi model mode to `high` or `off`. The default is `high`. |
| `--task TASK` | Select `profile` (default) or `sokoban`. |
| `-h`, `--help` | Show the command-line help and exit. No task starts. |

For example, set a 60-second task limit:

```powershell
uv run src/supervisor.py --limit-seconds 60
```

The task timer starts when the supervisor submits the prompt to Pi. The timer does not include model loading, network verification, or the Pi startup period. The supervisor allows up to 60 seconds for the startup readiness response. After a timeout, it allows up to five seconds for Pi to acknowledge the abort. Shutdown and cleanup can add time after the task deadline.

## Internal option: `--job-bootstrap`

Do not pass `--job-bootstrap` in a normal command. The supervisor passes it to a child copy of itself, together with a Windows Job Object handle and the agent command. The child joins the Job Object before it starts the Docker client. This lets the supervisor stop the processes in that job if an abort does not complete. The handle is an internal value for that launch. It is not a user parameter.

The Job Object controls the Windows client processes. The supervisor also removes the named Docker container on normal completion, interruption, or timeout. If the supervisor or Docker crashes, check Docker for a remaining `long-horizon-` container. Ollama remains outside the container. The gateway is stopped and the dedicated network removed during cleanup.

## Agent launch settings

The supervisor supplies these settings to Pi. They are not command-line options of `supervisor.py`:

| Setting | Current value | Purpose |
| --- | --- | --- |
| Model | `Qwen3.5-custom-32k` | Use the locally installed Ollama model. |
| Pi context window | `32768` | Require Ollama to allocate exactly this much context; Pi uses 32,768. |
| Thinking | `high` by default | Use `--thinking off` to disable thinking. The gateway sends the selected mode to Ollama. |
| Sampling | `Qwen3.5-custom-32k` settings | Preserve the model's saved sampling parameters; the gateway rejects request-level overrides. |
| Pi mode | `rpc` | Send the prompt and abort through Pi's RPC interface. |
| Pi session directory | `workspace/.pi-sessions/` within the run record | Retain Pi session files for this run. |

The default profile assignment remains in `experiment_workspace/task.prompt`. To run the separate one-box Sokoban pilot, use `uv run src/supervisor.py --task sokoban`. Its rules, environment, pushing example, and output instructions are in `sokoban_workspace/task.prompt`; the Sokoban workspace does not require `AGENTS.md`. The supervisor starts one game and owns its state. Each game starts with 24 actions; direction and undo attempts count even when blocked. `python3 src/play.py show` shows the labeled board, player, box and goal coordinates, remaining actions, and outcome. `python3 src/play.py history` shows the recorded action history. Neither command uses an action. The agent sends each move through `src/play.py`; the supervisor records it outside the agent's workspace and stops the agent immediately after action 24. There is no reset command. The game does not detect deadlocks or inject errors. Edit the appropriate task prompt to change an assignment. The model name and context are part of the gateway configuration as well as the supervisor; do not change one without updating the other. The supervisor does not provide command-line options for these settings.

The container has a read-only root filesystem, a writable temporary directory, and one writable host bind mount: the per-run workspace copy. Linux system files remain visible inside the container. It runs as a non-root user with capabilities dropped. When present, the copied `AGENTS.md` has its original Windows paths replaced with Linux instructions; its run-output rules remain. Links and Windows junctions in the source workspace are rejected before copying.

Each run copies its selected workspace, including any output folders. Changes to the copy are not merged back into the original workspace. The profile workspace uses its own `.run-version` counter; separate run copies can therefore have the same version number. For Sokoban, the supervisor creates an empty `output/` in the run copy before starting the model. If the copied workspace already has `output/`, preparation stops without overwriting it.

Pi runs on a dedicated Docker internal network in isolated gateway mode. Before the task starts, the supervisor verifies that the agent cannot reach Ollama or the public internet directly, that the gateway rejects Ollama management requests, and that private web destinations are blocked. A separate gateway container can access Ollama, but only forwards authenticated chat-completion requests for `Qwen3.5-custom-32k` with the selected thinking mode and no sampling overrides. For Sokoban it also relays authenticated game requests to the supervisor and checks that the game connection works before the task starts. It checks the loaded model digest and allocated context before each inference request. If the isolation check fails, the run stops before Pi receives the task.

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

## Records and outcomes

The supervisor prints the record directory at startup. Each started run under `supervisor-runs/` contains `events.jsonl`, `outcome.json`, `model.json`, and the copied `workspace/`. Sokoban runs also contain an authoritative `game.json` and `sokoban_rules.py` directly in the record directory, outside `workspace/`; deleting or editing workspace files does not reset the game. `sokoban_rules.py` is the exact copied source, including the board and rules, used by that run. The supervisor loads this snapshot before removing the source from the agent's workspace. Later project changes do not change the saved rules. To verify and display a saved state, run `uv run python <run-directory>/sokoban_rules.py --state <run-directory>/game.json show`. `model.json` records the model digest, saved parameters, and verified allocated context at startup. Pi session files use `workspace/.pi-sessions/`. A preparation failure can leave a workspace copy without event or outcome records. `events.jsonl` contains Pi lifecycle events and completed messages, tool calls, and tool results. It excludes `message_update` and `tool_execution_update` streaming fragments. A response interrupted mid-stream may have no complete message in this log. The supervisor prints non-JSON launcher output to the terminal, but does not retain it in `events.jsonl`. Terminal output can contain private information.

`outcome.json` records the limit, timestamps, elapsed task time when available, status, termination method, and launcher exit code. The status can be:

- `settled`: Pi stopped its run. This status does not prove task success.
- `timeout`: the task deadline expired. The termination value identifies a graceful abort acknowledgement or forced termination.
- `loop_detected`: ten consecutive calls to the same tool with identical arguments failed. `loop_detection` records the tool name, triggering call ID, and failure count. The supervisor requests an abort and uses forced termination if needed.
- `action_limit`: the Sokoban game recorded action 24. The supervisor immediately removes the agent container and terminates its client process. The authoritative game record is saved first.
- `startup_error`: the supervisor did not submit the prompt.
- `run_error`: the run ended unexpectedly after prompt submission.
- `interrupted`: the user interrupted the supervisor with Ctrl+C.

The supervisor returns exit code `0` for `settled` when container cleanup succeeds, and `1` otherwise. If immediate removal at the action limit fails, the outcome includes `immediate_container_stop: failed` and cleanup is retried. If final cleanup fails, the outcome includes `container_cleanup: failed`; check Docker for remaining `long-horizon-` containers or networks. Forced termination can leave partial output files. The records can contain prompts, tool results, and other session content. Keep them private and do not commit secrets.

For Sokoban, `outcome.json` also records the authoritative game outcome, number of actions, and limit in its `game` field. Every shutdown waits for an action already being saved and freezes the game before recording that summary; later requests cannot change the final state. If that pending action reaches action 24, the supervisor records `action_limit` and immediately stops the container. A solution on action 24 is recorded as `solved` even though the supervisor status is `action_limit`. Immediate termination can prevent the 24th response or the agent's report from being delivered; use the authoritative `game.json` to inspect the final state. `settled` does not mean the puzzle was solved. A timeout can also interrupt the agent before it writes its report.

The loop detector counts only tool results that Pi marks as errors. A successful call or a different tool call resets the count. The supervisor does not enforce the agent's output directory within the copy. It is non-interactive. To steer or resume a session, use Pi separately after the supervisor exits.

## Tests

Run the stand-in process tests with:

```powershell
uv run pytest
```
