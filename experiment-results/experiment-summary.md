# Long-horizon SLM experiments: master summary

Updated 30 October 2026. Times use Asia/Shanghai (UTC+8).
These runs are exploratory. They used different instructions, environments, and interventions.
The evidence does not establish a controlled comparison or a performance order.

## Output versions

| Version | Status at the original review | Primary findings | Report |
| --- | --- | --- | --- |
| 0 | Incomplete | Files matched two sessions. The timeline had ordering and consistency defects. The report was absent. | [Version 0 results](experiment-results-version-0.md) |
| 1 | Interrupted | The agent wrote to `output/`, not the requested run folder. It repeated two writes 437 times each. | [Version 1 results](experiment-results-version-1.md) |

The reports describe files present at the time of their original reviews.
The version 0 and version 1 output folders were absent from the workspace at the latest review.

## Supervised Ollama run

| Run | Outcome | Primary findings | Report |
| --- | --- | --- | --- |
| `20261030-100753-8ce2c174` | Incomplete | The agent read the seed but created no deliverables. Its last response hit the 16,384-token output limit. | [30 October run](experiment-results-20261030-100753.md) |
| `20261030-103850-af74bd43` | Incomplete | With `off` for thinking, the agent read the seed but made no deliverables. It left an empty file named `output`. | [Thinking-off run](experiment-results-20261030-103850.md) |

The supervisor recorded `settled`. That status does not establish task success.
The deadline and identical-call loop detector did not stop either run.

## Earlier sessions and evidence limits

The [version 1 report](experiment-results-version-1.md) covers the 13:48 session.
The retained files matched its writes, but the trace shows writes to `output/`.
The trace does not show how the files entered the versioned folder.

The 13:23 and 13:40 sessions contributed files to version 0. Its report records both sessions.
The [earlier exploratory sessions](early-exploratory-sessions.md) cover the 11:48 and 11:54 sessions.
The evidence does not link those earlier sessions to either output version.

The traces show repeated tool calls after errors or without progress.
A successful write does not establish that a file is correct.
The version 1 instructions did not fully agree. The evidence does not establish one cause for the loop.
Compaction occurred during the version 1 loop. The evidence does not show that compaction caused it.

No version has a confirmed successful end-to-end outcome.
The version 0 review did not include a complete source or browser audit.
The version 1 review did not include a full check of the artifacts.
Unsloth can remove temporary Pi traces. Keep copies of traces, prompts, settings, and artifacts for later analysis.
