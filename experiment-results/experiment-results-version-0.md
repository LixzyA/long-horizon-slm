# Experiment results: version 0

Reviewed 29 October 2026. The version label refers to the retained folder `output/run-version-0`, not a proven single Pi session. Times are Asia/Shanghai (UTC+8). This is an exploratory artifact and trace review, not a controlled evaluation.

## Outcome

**Incomplete, with substantive defects.** The folder has seven files: `sources.md`, `claims-audit.md`, `timeline.json`, `index.html`, `style.css`, `app.js`, and `README.md`. The requested `report.md` is absent. The README marks several requirements complete, but the saved artifacts do not substantiate those claims.

## Provenance: two sessions in one folder

Exact SHA-256 matches between the current artifacts and contents of recorded Pi write calls show:

- `timeline.json`, `index.html`, `style.css`, `app.js`, and `README.md` match writes from session `01a1861c-b3d1-72f5-9ab3-1d1ed67c7953` between 13:30:30 and 13:31:37. That session started at 13:23:10; the task prompt was submitted at 13:23:36.
- `sources.md` and `claims-audit.md` match writes from a later session, `01a1862c-1ff1-7228-b804-20822d33e270`, at 13:40:33 and 13:40:49. Its prompt was submitted at 13:40:18.
- Both sessions wrote to `output/` in their traces, not to `output/run-version-0/`. The mechanism and time at which the files were placed into the versioned folder are not established by these traces. Consequently the folder should not be analyzed as the untouched output of a single run.

Both traces name `unsloth/Qwen3.5-0.8B-GGUF`. Earlier local inspection of the 13:23 session's runtime recorded a 128,000-token model context; actual run settings for every session and model performance characteristics were not independently established for this report.

## Agent behavior

In the 13:23 session, a response hit a 32,000-token output limit at 13:27:23 while generating a `write` call; Pi reported that the truncated call was not executed. Later, the agent ran the same `python3` JSON validation pipeline 40 times. Its output reported that Python was not found. The user then instructed it to use `py`; the final recorded assistant event at 13:34:12 reports `This operation was aborted`. There are no compaction entries in this session's retained trace.

In the 13:40 session, the agent read the task and seed, then wrote the source ledger and audit. The final retained entry is the audit write result at 13:40:49, without a final response. Its reason for stopping is unverified.

## Artifact checks

- `timeline.json` parses as JSON and contains 12 entries, but is not chronologically sorted: its first date is `2015-09-06`, followed by `2005-11-09`. Entries use full dates while labeling precision as `ISO year`; their exact dates and factual support were not independently verified.
- `index.html` has a manually written timeline rather than one generated from the JSON. For example, it displays the BSc milestone with a 2015 date while the JSON gives that milestone a 2005 date. This breaks the requested single-data-source consistency.
- `app.js` selects `#searchForm`, but the HTML form has no `id="searchForm"`; the subsequent `addEventListener` therefore cannot attach to that element. The handler itself is a placeholder that logs the query. These are source-inspection findings; no browser test was performed.
- `sources.md` repeats the same sources as alternatives and describes `https://karpathy.ai/` as an official OpenAI website. The ledger's source claims and access dates cannot be accepted as independently verified from the retained evidence. The later claims audit also relies on the seed to support claims that were supposed to be checked.
- The site and README report a research date of 15 January 2024, and the audit reports a 2024 date. The observed Pi runs occurred in 2026; the source record does not establish that those dates are actual access dates.
- The requested category filter, meaningful search, report, end-to-end browser checks, and source verification were not established. No live source checks or comprehensive accessibility or website tests were performed for this report.

## Evidence and artifact fingerprints

Pi traces:

- `C:/Users/felix/.unsloth/studio/auth/agents/.tmp/unsloth-pi-wdzfi3kq/.pi/agent/sessions/--C--Project-long-horizon-slm--/2026-10-29T05-23-10-425Z_01a1861c-b3d1-72f5-9ab3-1d1ed67c7953.jsonl`
- `C:/Users/felix/.unsloth/studio/auth/agents/.tmp/unsloth-pi-lhi7eh6_/.pi/agent/sessions/--C--Project-long-horizon-slm--/2026-10-29T05-40-01-144Z_01a1862c-1ff1-7228-b804-20822d33e270.jsonl`

Current `output/run-version-0` files, SHA-256:

| File | SHA-256 |
| --- | --- |
| app.js | `28bfbf13b76cb4706f889621a3428534feac485fc26b545d64f051f7ed2512fd` |
| claims-audit.md | `095476d52e00a46532f49fead99f4b1facf8dc99540729f1e688593719e708ea` |
| index.html | `1d16be814076a47182be26655c2472ef38a154f525f87b21eabe042ce96e8e72` |
| README.md | `34d1e35038ed7de0ed7d073e3a578737d4b1894486640e3fb6bdcdc0cdec523` |
| sources.md | `a10d2790724c6d9f5f1420b548a7dfa63600b3ff68b74b87c8b322797b12abbe` |
| style.css | `cb93db2dfe410958fdeb08a93cc4926966e1895ce060899fd94c1291a20ad005` |
| timeline.json | `c7502e318e0245ac94e0a0c366e89ebd3e7ccd0c130006ef7b1f6d9a9681251d` |

Trace files are under Unsloth's temporary directory and may be cleaned up. A hash establishes content identity, not that the agent's claims or checks were correct.