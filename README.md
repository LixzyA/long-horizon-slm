# Project description
This is a project for researching long horizon tasks on small language models. The first few experiment is run on Qwen3.5-0.8B-GGUF.

# Supervised Pi run

The supervisor starts one Pi task on Windows. It sends the prompt in RPC mode and stops the run at the time limit. It uses `experiment_workspace/` as Pi's working directory. Pi reads the task from `experiment_workspace/task.prompt`.

## Prerequisites

1. Start Unsloth Studio and load the intended model.
2. Make sure that `unsloth` and `pi` are available on `PATH`.
3. From the project directory, install the project environment:

   ```powershell
   uv sync
   ```

## Command-line options

Start the supervisor with the default limit of 2,700 seconds (45 minutes):

```powershell
uv run src/supervisor.py
```

| Option | Description |
| --- | --- |
| `--limit-seconds SECONDS` | Set the maximum task time in seconds. The value must be a positive, finite number. The default is `2700`. |
| `-h`, `--help` | Show the command-line help and exit. No task starts. |

For example, set a 60-second task limit:

```powershell
uv run src/supervisor.py --limit-seconds 60
```

The task timer starts when the supervisor submits the prompt to Pi. The timer does not include the Pi startup period. The supervisor allows up to 60 seconds for the startup readiness response. After a timeout, it allows up to five seconds for Pi to acknowledge the abort. Shutdown and cleanup can add time after the task deadline.

## Internal option: `--job-bootstrap`

Do not pass `--job-bootstrap` in a normal command. The supervisor passes it to a child copy of itself, together with a Windows Job Object handle and the agent command. The child joins the Job Object before it starts Unsloth and Pi. This lets the supervisor stop the processes in that job if an abort does not complete. The handle is an internal value for that launch. It is not a user parameter.

A Windows Job Object groups the owned processes. It is not a filesystem or network sandbox. The supervisor does not intentionally stop an Unsloth Studio server that is already active.

## Agent launch settings

The supervisor supplies these settings to Unsloth and Pi. They are not options of `supervisor.py`:

| Setting | Current value | Purpose |
| --- | --- | --- |
| `--model` | `unsloth/Qwen3.5-0.8B-GGUF` | Select the model. |
| `--context-length` | `128000` | Request the model context length through Unsloth. |
| `--persist` | Enabled | Keep Unsloth-managed Pi session data. |
| `--no-serve` | Enabled | Require an existing Unsloth server. Do not start a server automatically. |
| `--mode` | `rpc` | Use Pi's RPC interface for the prompt and abort commands. |
| `--session-dir` | A `pi-sessions` folder inside the supervisor record directory | Store Pi session files for this run. |
| `--repeat-penalty`| 1.15 | To avoid the agent having a loop |

Change the model, context length, or prompt in `src/supervisor.py`. The supervisor does not provide command-line options for these settings.

The Python function `supervise()` has these parameters. They are not command-line options:

| Parameter | Description |
| --- | --- |
| `command` | The agent launch command as a list of arguments. |
| `prompt` | The task text to send to Pi. |
| `limit_seconds` | The task deadline in seconds. |
| `run_dir` | The directory for the event and outcome records. |
| `grace_seconds` | The wait for abort acknowledgement and process cleanup. The default is `5`. |
| `startup_seconds` | The maximum wait for Pi's readiness response. The default is `60`. |

## Records and outcomes

The supervisor prints the record directory at startup. Each directory under `supervisor-runs/` contains `events.jsonl` and `outcome.json`. Pi session files use the `pi-sessions/` subdirectory when Pi creates them. `events.jsonl` contains JSON records received from Pi. Non-JSON launcher output is not retained there.

`outcome.json` records the limit, timestamps, elapsed task time when available, status, termination method, and launcher exit code. The status can be:

- `settled`: Pi stopped its run. This status does not prove task success.
- `timeout`: the task deadline expired. The termination value identifies a graceful abort acknowledgement or forced termination.
- `startup_error`: the supervisor did not submit the prompt.
- `run_error`: the run ended unexpectedly after prompt submission.
- `interrupted`: the user interrupted the supervisor with Ctrl+C.

The supervisor returns exit code `0` for `settled` and `1` for the other recorded outcomes. Forced termination can leave partial output files. The records can contain prompts, tool results, and other session content. Keep them private and do not commit secrets.

The supervisor does not detect repeated tool calls. It does not enforce the agent's output directory. It is non-interactive. To steer or resume a session, use Pi separately after the supervisor exits.

## Tests

Run the stand-in process tests with:

```powershell
uv run pytest
```
