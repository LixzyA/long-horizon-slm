# Long-horizon SLM experiments: master summary

Updated 29 October 2026. This index records the two output versions identified by the user. Times are Asia/Shanghai (UTC+8). These are exploratory observations; the sessions were not a controlled comparison and differed in instructions, intervention, and artifact provenance.

| Version | Retained output | Status | Main observations | Detailed record |
| --- | --- | --- | --- | --- |
| 0 | `output/run-version-0/` | Incomplete; files match two different sessions | One session hit an output limit and repeated a failing Python check. The saved timeline is unsorted, the search is a placeholder, the report is absent, and source claims are not established. | [Version 0 results](experiment-results-version-0.md) |
| 1 | `output/run-version-1/` | Interrupted; repeated-write loop | The 13:48 session wrote directly to `output/` despite receiving a run-folder instruction; it repeated writes to each of two files 437 times, and 16 compaction entries were recorded before the aborted final event. | [Version 1 results](experiment-results-version-1.md) |

## Scope and earlier sessions

The [version 1 report](experiment-results-version-1.md) covers the 13:48 session. Its retained files match that session's writes, which targeted `output/`; the trace does not show how they were placed in the versioned folder. The 13:23 and 13:40 sessions contributed files to version 0 and are documented in its report. The 11:48 and 11:54 sessions are preserved separately in [earlier exploratory sessions](early-exploratory-sessions.md); their association with either output version is unverified.

## Shared observations

- The traces document repeated tool use after errors or without progress. A successful write does not demonstrate a correct artifact.
- The prompt and environment changed over time, and the run-folder instructions conflicted with the task prompt during the version 1 session. These results do not identify a single cause or establish a performance ranking.
- Compaction in version 1 did not stop its write loop. The evidence does not establish that compaction caused the loop.
- Neither version has an independently established successful end-to-end outcome. The version 0 report is a bounded artifact inspection, not a complete source or browser audit; the version 1 record does not include a full artifact verification.
- Temporary Pi traces may be removed by Unsloth. Preserve copies, prompts, configuration, and before/after artifacts before future evaluations if reproducibility matters.