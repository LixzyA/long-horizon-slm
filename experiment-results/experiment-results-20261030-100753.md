# Experiment results: Ollama run on 30 October 2026

This report covers supervisor run `20261030-100753-8ce2c174`.
Times use Asia/Shanghai (UTC+8). This was an exploratory run.

## Outcome

**Incomplete.** The agent did not create the output folder or any deliverables in the copied workspace.
The copied `.run-version` file contained `3`. The next folder was `output/run-version-4`.
The supervisor recorded `settled` and `normal`. These values show that Pi stopped, not that the task succeeded.

## Run settings

- The model was `qwen-custom` in Ollama. Its digest was `7bdc5f1ec887d0f54e92e907de7b6d205cb9610a82b6b5b4ebf32c3127d0fcdd`.
- The allocated model context was 131,072 tokens. Pi used a 128,000-token context window.
- Pi used `high` for `thinkingLevel`. The maximum output for one response was 16,384 tokens.
- The model parameters were temperature `1`, top-p `0.95`, top-k `20`, and min-p `0`.
- The parameters also included repetition penalty `1.15`, presence penalty `1.5`, and `draft_num_predict` `2`.
- The supervisor used a Docker workspace copy. It supplied the full assignment in the prompt.
- The time limit was 2,700 seconds. The task elapsed time was 274.531 seconds.
- Pi session `01a18a90-5355-7505-a160-ce6b6b33e8b3` started at 10:07:56.
- The supervisor sent the prompt at 10:07:56. The run ended at 10:12:31.

## Agent actions

1. The agent read `input/andrej.md` as its first tool call. The tool returned the seed text.
2. The agent made 18 tool calls: one `read` call and 17 `bash` calls.
3. The agent searched for profile data in Pi files under `/opt/pi`. These files were inside the container.
4. The agent attempted one `curl` request. The trace does not show a successful response from a source.
5. The agent made six consecutive calls that Pi marked as errors. The calls had different commands.
6. The final tool call attempted to write a draft to `/tmp/README_karthie.md`. Pi marked the command as an error.
7. The draft asserted that source checks were complete. The trace does not support that assertion.
8. The attempted draft also contained an incorrect name and a research date from 2025.

The trace does not show a call to read or update `.run-version`.
It does not show the creation of a deliverable in the copied workspace.
Shell fallback commands and pipelines caused some calls to return success despite error text.

## Stop condition

The final assistant response had `stopReason: length` and `rawStopReason: length`.
Pi reported 16,384 output tokens for that response. The response contained a `thinking` block and no final text or tool call.
The response took 208.537 seconds. Pi then emitted `agent_end` and `agent_settled`.
The supervisor set the status to `settled` when it received `agent_settled`.

This was an output limit for one response. The trace does not show a 128,000-token context limit.
The 2,700-second deadline did not stop the run. The loop detector did not stop it.
The six errors had different commands, so they did not meet the identical-call rule.

The event log excludes `message_update` and `tool_execution_update` fragments. It cannot show all intermediate output from the final response.

## Evidence and limits

- [Outcome](../supervisor-runs/local/20261030-100753-8ce2c174/outcome.json)
- [Model settings](../supervisor-runs/local/20261030-100753-8ce2c174/model.json)
- [Event trace](../supervisor-runs/local/20261030-100753-8ce2c174/events.jsonl)
- [Copied assignment](../supervisor-runs/local/20261030-100753-8ce2c174/workspace/task.prompt)
- Pi session: `workspace/.pi-sessions/2026-10-30T02-07-56-758Z_01a18a90-5355-7505-a160-ce6b6b33e8b3.jsonl` in the run folder.

The workspace check found no `output` directory. The container is no longer available.
The trace cannot establish which temporary files remained in `/tmp` before container removal.
No live source check or browser test was done for this report.
The run records are local and untracked. Keep them if later analysis is necessary.
