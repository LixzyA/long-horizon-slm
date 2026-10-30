# Experiment results: Ollama run with thinking off

This report covers supervisor run `20261030-103850-af74bd43`.
Times use Asia/Shanghai (UTC+8). This was one exploratory run.

## Outcome

**Incomplete.** The agent did not create the required deliverables.
The copied workspace contains an empty file named `output`.
The task required an output folder, not an empty file.
The supervisor recorded `settled` and `normal`. These values do not establish task success.

## Run settings

- The model was `qwen-custom` in Ollama.
- The model digest was `7bdc5f1ec887d0f54e92e907de7b6d205cb9610a82b6b5b4ebf32c3127d0fcdd`.
- The allocated model context was 131,072 tokens. Pi used a 128,000-token context window.
- Pi used `off` for `thinkingLevel`. The gateway sent `reasoning_effort: none` to Ollama.
- The maximum output for one response was 16,384 tokens.
- The model parameters included temperature `1`, top-p `0.95`, top-k `20`, and min-p `0`.
- The parameters also included repetition penalty `1.15`, presence penalty `1.5`, and `draft_num_predict` `2`.
- The supervisor supplied the task prompt in a Docker workspace copy.
- The time limit was 2,700 seconds. The task elapsed time was 295.297 seconds.
- The supervisor sent the prompt at 10:38:55. The run ended at 10:43:51.

## Agent actions

1. The first tool call tried to read `/input/andrej.md`. That path did not exist.
2. The agent found and read `/workspace/input/andrej.md`.
3. The agent then searched for a different name, `Anderj Sofary`, in archive URLs.
4. The agent made 14 tool calls. Pi marked nine calls as errors.
5. Some shell commands contained syntax errors. The image did not contain `curl`.
6. One command returned success even though its output said that `curl` was absent.
7. Pi retried one model response after the stream ended without a finish reason.
8. The agent left an empty file named `output`. It did not create the required folder.

The trace does not show a call to read or update `.run-version`.
The trace does not establish the cause of the incorrect name or the empty file.

## Stop condition

The final assistant response had `stopReason: stop` and `rawStopReason: stop`.
The response stated an intent to try another approach. It contained no tool call.
Pi then emitted `agent_end` and `agent_settled`.
The supervisor did not stop the run for the time limit or the identical-call loop limit.

Pi recorded 12,633 output tokens for the final response and 107 characters of visible text.
The trace does not explain this difference. The response did not contain a `thinking` block.
The trace does not establish how Ollama used those output tokens.

## Comparison with the previous run

| Measure | Previous run | This run |
| --- | --- | --- |
| Pi thinking level | `high` | `off` |
| Task result | Incomplete | Incomplete |
| Tool calls | 18 | 14 |
| Final stop reason | `length` | `stop` |
| Task elapsed time | 274.531 seconds | 295.297 seconds |

The two runs used the same model digest, saved model parameters, seed, task prompt, and `.run-version` input.
Each condition has one run. These results do not establish that either condition performs better.

## Evidence and limits

- [Outcome](../supervisor-runs/20261030-103850-af74bd43/outcome.json)
- [Model settings](../supervisor-runs/20261030-103850-af74bd43/model.json)
- [Event trace](../supervisor-runs/20261030-103850-af74bd43/events.jsonl)
- [Copied task](../supervisor-runs/20261030-103850-af74bd43/workspace/task.prompt)
- [Previous run report](experiment-results-20261030-100753.md)

The event log excludes streamed fragments. It cannot show all intermediate model output.
The run records are local and untracked. No live source audit was done for this report.
