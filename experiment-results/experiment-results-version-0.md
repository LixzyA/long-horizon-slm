# Experiment results: version 0

This report records a review from 29 October 2026. Times use Asia/Shanghai (UTC+8).
The version label refers to the folder `output/run-version-0`.
The evidence does not link that folder to one Pi session.
This was an exploratory review, not a controlled evaluation.

## Outcome

**Incomplete, with defects.** At the time of review, the folder contained seven files.
They were `sources.md`, `claims-audit.md`, `timeline.json`, `index.html`, `style.css`, `app.js`, and `README.md`.
The requested `report.md` was absent. The README marked several requirements as complete.
The saved files did not support those completion claims.
Those version 0 files are not in the current workspace.

## File provenance

SHA-256 matches linked the contents of saved files to Pi write calls:

- `timeline.json`, `index.html`, `style.css`, `app.js`, and `README.md` matched session `01a1861c-b3d1-72f5-9ab3-1d1ed67c7953`.
  Those calls occurred between 13:30:30 and 13:31:37. The session started at 13:23:10.
  The user submitted the prompt at 13:23:36.

- `sources.md` and `claims-audit.md` matched the later session `01a1862c-1ff1-7228-b804-20822d33e270`.
  The calls occurred at 13:40:33 and 13:40:49. The user submitted the prompt at 13:40:18.

- Both traces show writes to `output/`, not to `output/run-version-0/`.
  The traces do not show when or how the files entered the versioned folder.
  The folder is therefore not evidence of the untouched output of one session.

Both traces name `unsloth/Qwen3.5-0.8B-GGUF`.
An earlier local inspection recorded a 128,000-token context for the 13:23 session.
The original review did not establish the settings for every session or model performance.

## Agent actions

At 13:27:23, a response in the 13:23 session hit a 32,000-token output limit.
The model attempted a `write` call. Pi reported that it did not execute the truncated call.
The agent later ran the same `python3` JSON validation pipeline 40 times.
The output reported that Python was not found.

The user then instructed the agent to use `py`.
At 13:34:12, the final recorded assistant event reported `This operation was aborted`.
The retained trace has no compaction entries for this session.

In the 13:40 session, the agent read the task and seed. It then wrote the source ledger and audit.
The last retained entry was the audit write result at 13:40:49. There was no final response.
The reason that the session stopped is unknown.

## Artifact checks

- `timeline.json` parsed as JSON and contained 12 entries. The dates were not in chronological order.
  Its first date was `2015-09-06` and its second date was `2005-11-09`.
  Entries used full dates with the precision label `ISO year`. Their exact dates and factual support were not independently checked.

- `index.html` contained a manual timeline, not one made from the JSON.
  It showed the BSc milestone with a 2015 date. The JSON gave that milestone a 2005 date.
  Thus, the two files did not use one consistent source of timeline data.

- `app.js` selected `#searchForm`. The HTML form had no `id="searchForm"`.
  The subsequent `addEventListener` call failed because the selected element was absent.
  The handler only logged the query. These findings came from source inspection, not a browser test.

- `sources.md` repeated the same sources as alternatives. It called `https://karpathy.ai/` an official OpenAI website.
  The retained evidence did not independently confirm the source claims or access dates.
  The later claims audit also used the seed to support claims that needed independent checks.

- The site and README gave a research date of 15 January 2024. The audit also gave a 2024 date.
  The Pi sessions occurred in 2026. The evidence does not establish that those dates were actual access dates.

- The review did not establish a usable category filter, meaningful search, or a report.
  It did not establish complete browser checks or source verification.
  No live source checks or complete accessibility and website tests occurred for the report.

## Evidence and file fingerprints

Pi traces:

- `C:/Users/felix/.unsloth/studio/auth/agents/.tmp/unsloth-pi-wdzfi3kq/.pi/agent/sessions/--C--Project-long-horizon-slm--/2026-10-29T05-23-10-425Z_01a1861c-b3d1-72f5-9ab3-1d1ed67c7953.jsonl`
- `C:/Users/felix/.unsloth/studio/auth/agents/.tmp/unsloth-pi-lhi7eh6_/.pi/agent/sessions/--C--Project-long-horizon-slm--/2026-10-29T05-40-01-144Z_01a1862c-1ff1-7228-b804-20822d33e270.jsonl`

The SHA-256 values below describe the files at the time of the original review.

| File | SHA-256 |
| --- | --- |
| app.js | `28bfbf13b76cb4706f889621a3428534feac485fc26b545d64f051f7ed2512fd` |
| claims-audit.md | `095476d52e00a46532f49fead99f4b1facf8dc99540729f1e688593719e708ea` |
| index.html | `1d16be814076a47182be26655c2472ef38a154f525f87b21eabe042ce96e8e72` |
| README.md | `34d1e35038ed7de0ed7d073e3a578737d4b1894486640e3fb6bdcdc0cdec523` |
| sources.md | `a10d2790724c6d9f5f1420b548a7dfa63600b3ff68b74b87c8b322797b12abbe` |
| style.css | `cb93db2dfe410958fdeb08a93cc4926966e1895ce060899fd94c1291a20ad005` |
| timeline.json | `c7502e318e0245ac94e0a0c366e89ebd3e7ccd0c130006ef7b1f6d9a9681251d` |

Unsloth can remove the temporary traces. A hash shows content identity.
A hash does not establish that the agent's claims or checks were correct.
