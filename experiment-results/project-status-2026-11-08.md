# Long-horizon SLM project: current status

Snapshot: 8 November 2026, approximately 12:55, Asia/Shanghai (UTC+8). This is an exploratory research record, not evidence of comparative performance or a completed fine-tuning study.

## Objective and current stage

The project investigates small language models on tasks requiring dependent decisions over many steps. A particularly useful question is whether post-training can improve recognition of mistakes and recovery after feedback arrives. The current task is a controlled one-box Sokoban pilot. The environment and data collection exist; no fine-tuning or post-training evaluation has yet been performed as part of the work described here.

The first four recent boards were solved once each. A new, more difficult board exposed both a planning/recovery failure and a context-management limit. There is now a plausible capability to study, but one completed harder-board trial is not enough to estimate a success rate or select a training method.

## Experiment setup

- Model: Qwen3.5 4.2B Q4_K_M text GGUF, served by the pinned llama.cpp build b12110; 32,768-token context, one slot, GPU offload, and f16 key/value cache. The run metadata records the exact model and backend identity.
- Agent: Pi 1.4.0, with thinking `high` in the runs below. The seed is random. The supervisor runs Pi in an isolated Docker workspace and owns the Sokoban state outside that workspace.
- Task: one action per command, with no reset. Direction and undo attempts consume the action budget even when blocked; `show` and `history` do not. The game provides board state and outcome but does not identify deadlocks or inject mistakes.
- Records: each run has an authoritative `game.json`, puzzle snapshot, model metadata, event log, and outcome when the supervisor has finished. `settled` describes agent termination; it does not mean the board was solved.
- Current project changes: the `detour` board, CLI choice, tests, and README updates are uncommitted. The ordinary suite run after the addition reported **154 passed, 6 skipped**; the skipped integration tests were not a model-performance evaluation.

See [project README](../README.md), [training puzzle definitions](../src/sokoban/puzzles-train.json), and [task prompt](../sokoban_workspace/task.prompt).

## Completed pilot results

Each row is one run, so these are observations rather than reliable success rates. Times below are elapsed task time, not model startup time.

| Local start time, 8 Nov | Puzzle | Game result | Actions / limit | Elapsed | Evidence |
| --- | --- | --- | --- | --- | --- |
| 12:00 | one-push | Solved | 1 / 8 | 22.9 s | [Outcome](../supervisor-runs/local/20261108-120014-a4d36eb1/outcome.json) |
| 12:01 | align | Solved | 2 / 12 | 39.6 s | [Outcome](../supervisor-runs/local/20261108-120124-c0006e3d/outcome.json) |
| 12:14 | baseline | Solved | 14 / 24 | 149.8 s | [Outcome](../supervisor-runs/local/20261108-121432-f7030672/outcome.json) |
| 12:20 | offset | Solved | 7 / 28 | 86.0 s | [Outcome](../supervisor-runs/local/20261108-122047-dcac6e2b/outcome.json) |
| 12:34 | detour | In progress when agent stopped | 47 / 60 | 429.0 s | [Outcome](../supervisor-runs/local/20261108-123447-a37f87be/outcome.json) |

In `baseline`, the model first pushed the box into a dead end, used three undos, and then solved the board. The game record contains no blocked direction attempts in that run, even though its generated report describes blocked moves. Use `game.json`, not the generated report, for action counts.

The new `detour` board has a verified shortest solution of 26 actions, compared with 7 for `offset`. A solution requires a push that increases the box's distance from the goal. Its 60-action budget is a pilot choice, allowing room for mistakes and undo; the boards and limits are not a validated difficulty scale. The game test checks the shortest path and replay against the authoritative rules.

## First completed detour run

The [game record](../supervisor-runs/local/20261108-123447-a37f87be/game.json) shows 34 successful moves, 11 blocked attempts, and two successful undo actions. After pushing the box against the top wall, the model continued trying to find a route around it; the two undos did not reverse that box push. The supervisor recorded `settled`, but the authoritative outcome remained `in_progress` with 13 actions unused. There was no final report in the run's output directory.

The final assistant response had stop reason `length` and consisted of one generated token. The backend logged a final prompt of 28,840 tokens in the 32,768-token context. The installed Pi 1.4.0 source uses a 4,096-token safety allowance when calculating the response budget, with a minimum of one token. This is consistent with the observed stop, but the exact outgoing request's token limit was not retained, so the cause remains an inference. It was not the 60-action limit or task timeout. The usual configured maximum of 16,384 output tokens is per model response, not a total budget for the entire experiment; raising that maximum alone would not create more context room.

The final recorded conversation contained approximately 45,312 characters of assistant thinking, 17,172 characters of tool-result text, and 5,062 characters in the task prompt. These are character counts, not token counts. The prompt explicitly requests detailed thinking per action; reducing that output is a candidate intervention, not a change that has already been tested.

Sources: [events](../supervisor-runs/local/20261108-123447-a37f87be/events.jsonl), [server log](../supervisor-runs/local/20261108-123447-a37f87be/llama-server.log), [outcome](../supervisor-runs/local/20261108-123447-a37f87be/outcome.json).

## Newer run: provisional snapshot

A second `detour` run, [20261108-124837-1d1c0ba1](../supervisor-runs/local/20261108-124837-1d1c0ba1/), had no `outcome.json` at the time of this snapshot. Its saved game showed **28 of 60 actions used**, with the box at row 1, column 2. The records were still being updated shortly before inspection. This is a provisional state, not a completed result; check the final outcome and full event log before interpreting it. Its copied prompt matches the current template with the action limit substituted, and its metadata records thinking `high`.

## Hardware and context

On the RTX 3060 Laptop GPU with 6,144 MiB VRAM, the completed detour run's server startup projected 3,695 MiB of GPU allocation: 2,515 MiB model, 1,074 MiB context, and 106 MiB compute. It reported 5,130 MiB free VRAM before loading and offloaded all 33 layers. The same log reported approximately 15.4 GiB visible system memory and 3.8 GiB free at startup. Its initial 549 MiB host estimate is not a measured peak; checkpoints, Pi, Docker, and other processes also use RAM. A larger context would require additional memory and a verified configuration; no 64k run has been measured.

## Research interpretation

The detour trajectory gives concrete candidate training targets: detect an irreversible or costly push before committing, recognize a deadlock after feedback, undo back to a useful state, and replan within an action budget. These remain hypotheses. The current board gives immediate observations and allows undo; it does not yet isolate delayed feedback, and the run also ended due to a likely context-budget constraint. Failure cannot be attributed to one cause without controlled follow-up.

A model that fails a board is not by itself evidence that fine-tuning will improve it. A useful evaluation needs multiple independent runs and multiple structurally varied boards, with held-out puzzles kept separate from any training trajectories. Keep the backend, model, prompt, sampling, action and time budgets, thinking mode, and context policy recorded for each condition. Do not compare the older Ollama profile experiments as if they were the same setup.

## Recommended next steps

1. Finish and review the newer run before adding it to the completed-results table. Record whether it ended by solving, action limit, timeout, error, or context-related length stop.
2. Establish a repeated baseline on several distinct boards, including detour-like cases, before choosing training. Track solve rate, actions and blocked attempts, deadlocks, successful recovery after a mistake, and context-related stops. Preserve run-level outcomes, not just averages.
3. Test a shorter per-action reasoning instruction while retaining the full board and one action per command. Compare it with the current prompt as a separately labeled condition. Thinking `off` is another condition, not a directly interchangeable continuation of the baseline.
4. Design a separate recovery evaluation, potentially with controlled starting mistakes or delayed feedback, and verify that each starting state can be recovered within its budget. Decide later whether the data supports supervised fine-tuning, another post-training method, or an environment/prompt fix.
5. Keep evaluation boards and trajectories separate from training material. Record any prompt, context handling, backend, or model changes so improvements remain interpretable.

Earlier profile-task experiments are summarized in [the historical master summary](experiment-summary.md). They used different setups and did not establish a completed successful end-to-end profile task.
