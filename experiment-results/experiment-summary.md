# Master report: long-horizon small language model research

Last reviewed: 8 November 2026, approximately 16:50, Asia/Shanghai (UTC+8).

This file is the master record for the project. It gives the research history, experiment results, current limits, and next steps. The linked reports and run records give the detailed evidence. New reports must add their key results and links here. Past results must retain their original conditions and uncertainty.

## Current state

The project studies whether `post-training` can improve a small model on dependent tasks that require many decisions. A particular interest is recovery from earlier mistakes when feedback is delayed or incomplete. The current experiment uses one-box Sokoban as a small, observable pilot. The supervisor now supports Sokoban only. Earlier profile runs remain in the historical records.

The first four recent Sokoban boards each had one successful run. Five completed local runs on the harder `detour` board ended without a solution. Three `high` runs stopped with `length`. Two `off` runs reached the action limit. One of the `high` runs used the concise prompt.

Later `off` runs solved `one-push`, `align`, and `baseline`. Each easy board has one run per mode. These observations do not establish which mode is better or the effect of `fine-tuning`.

A hosted DeepSeek V4.1 Flash pilot solved all five boards at least once across eight runs. Three attempts stopped before an action. See the [DeepSeek pilot report](deepseek-v4-1-flash-sokoban-2026-11-08.md) for conditions and limits.

No `post-training` experiment is documented in the reviewed project records. The current Sokoban environment gives an immediate board observation and allows undo. It does not yet isolate delayed feedback. A controlled recovery study and held-out evaluation set remain future work.

## Research origin: 28 October

The initial research discussion focused on the model, not only the agent workflow. The proposed question was whether a small model can learn to detect and recover from its own earlier errors. A possible comparison included the base model, ordinary successful-task `fine-tuning`, and recovery-focused `fine-tuning` on unseen tasks and error cases.

The broad topic was not presented as new. A narrower comparison of immediate error messages with delayed or indirect evidence was a possible research direction, not a verified novelty claim. A small local model and parameter-efficient `fine-tuning` were possible pilot choices. The memory to train a model and the feasibility were not measured. The 28 October discussion did not implement code or an experiment.

Source: the 28 October research-session summary in local Codex memory. The original discussion was outside this repository.

## Project history

### 29 October: profile task and early Pi sessions

The first retained sessions used a sourced Andrej Karpathy profile and local website task. In the 11:48 session, the agent tried incorrect paths. The last retained event did not show the result of a filesystem search. In the 11:54 session, a filesystem search aborted after about 369 seconds. An earlier trace review also found at least 110 repeated package-install commands. The final result of that session is unknown.

The version 0 artifact folder combined content that matched writes from two Pi sessions. At the original review, it had seven files but no requested `report.md`. The timeline and site had inconsistent data, and source checks were incomplete. The files were not present at the latest review. The traces did not show how files entered the versioned folder.

The version 1 session ended as aborted. Its trace contained 437 writes to each of two files and 16 compaction entries. The trace does not prove that compaction caused the repeated writes. The task and run-folder instructions did not fully agree. A complete end-to-end review did not establish task success.

Detailed reports: [early sessions](early-exploratory-sessions.md), [version 0](experiment-results-version-0.md), and [version 1](experiment-results-version-1.md).

The project then added a supervisor for Pi, a copied Docker workspace, a deadline, a repeated-failure detector, retained event records, and cleanup. Two retained supervisor runs on 29 October ended with `loop_detected` after ten identical failed calls. Their outcomes are in the run index below.

### 30 October: supervised Ollama profile runs

The project used Ollama `qwen-custom` with Pi and a 128,000-token Pi context. In one `high` run, the agent produced no deliverables. Its final response reached the 16,384-token per-response output limit. In one `off` run, the agent also produced no deliverables and left an empty file named `output`. Pi ended the second run with `stop`.

Both supervisor outcomes said `settled`. Neither status established task success. Each condition had one run. The results do not establish which mode performed better.

Detailed reports: [high mode](experiment-results-20261030-100753.md) and [off mode](experiment-results-20261030-103850.md).

### 5–7 November: Sokoban and backend changes

The project moved to a one-box Sokoban task with a finite action budget. Later changes moved game state to the supervisor, retained rules and state snapshots, and strengthened run isolation and model records. Git history records a transition from Ollama to an owned llama.cpp backend on 7 November. The backend change is a new experimental condition.

The run index lists the retained 5 November records. Their supervisor statuses are available, but this master report does not claim task success from those statuses. Their game and output files need a separate review before we classify the task results. A 7 November run reached its 24-action limit without a solution. Another 7 November directory has no final outcome record.

### 8 November: selectable boards and detour pilot

The project added four selectable pilot boards. One run solved each board. The baseline board included an early box deadlock and three undo actions before success. The `offset` board was solved in seven actions.

We added `detour` as a harder board. Its shortest solution is 26 actions, and a solution requires a push away from the goal. The action limit is 60. This limit is a pilot choice, not a validated difficulty scale. The ordinary project test suite reported **154 passed and 6 skipped** after this addition.

The skipped tests included optional integration checks. These tests do not measure model task performance.

The first two completed `detour` runs did not solve the board. Both ended with `length` and one output token in the final response. The table below records the authoritative game result.

| Run start | Board | Result | Actions / limit | Notes |
| --- | --- | --- | --- | --- |
| 12:00 | `one-push` | Solved | 1 / 8 | One run. |
| 12:01 | `align` | Solved | 2 / 12 | One run. |
| 12:14 | `baseline` | Solved | 14 / 24 | Three undo actions. |
| 12:20 | `offset` | Solved | 7 / 28 | One run. |
| 12:34 | `detour` | In progress when agent stopped | 47 / 60 | 11 blocked moves and two successful undos. |
| 12:48 | `detour` | In progress when agent stopped | 35 / 60 | Seven blocked moves, three successful undos, and one empty undo. |

The first detour run pushed the box against the top wall, then continued to search for a route. Its two undo actions did not reverse that push. The second run ended with the box in the same top-row position. These records show difficulty with the task. They do not identify a single cause or prove the effect of a method to train the model.

The first detour run's final backend prompt had 28,840 tokens. The second had 28,875 tokens. Both used a 32,768-token context. Installed Pi source reserves 4,096 tokens when it calculates response space, down to a one-token minimum.

That rule is consistent with both final responses. The exact request limits were not retained, so this explanation remains an inference. The action and time limits did not end these runs.

The first detour conversation had about 45,312 characters of assistant `thinking` and 17,172 characters of tool results. These are character counts, not token counts. The standard prompt requests detailed `reasoning` for each action. A separate concise prompt is now available. A `high` run with that prompt later stopped with `length` at 51 actions.

Detail: [8 November status snapshot](project-status-2026-11-08.md). Its 12:55 snapshot correctly marked the second detour run as unfinished at that time. This master report records its later final outcome.

### 8 November, 13:02: detour with thinking off

The first reviewed `off` run reached 60 of 60 actions without a solution. The box did not move. After action 6, the player stayed in two squares and made repeated blocked attempts. The run had 24 blocked moves and no undo. Five transient gateway 503 errors each had a successful retry. The first error came after the movement loop began.

The model wrote an in-progress report at action 9. It did not update that file before the supervisor stopped the agent at action 60. The supervisor-owned outcome and game state give the final count. The current loop detector did not stop the sequence because blocked game moves were successful tool calls, and the commands alternated.

A GPT-6.1 Sol agent with high `reasoning` effort reviewed the trace. The run is one sample and does not establish the relative performance of `off` and `high`. Detailed evidence: [13:02 detour report](experiment-20261108-130242.md).

### 8 November, 13:47–13:53: mode comparison

Three new `off` runs solved `one-push`, `align`, and `baseline`. They used 1, 6, and 14 actions, respectively. The earlier `high` runs used 1, 2, and 14 actions on the same boards. The `off` runs used 0, 1, and 3 undo actions. The `high` runs used 0, 0, and 3.

The saved pairs match on board, prompt, model hash, backend executable, image, context, and sample settings. The seed is random. Each pair has one run per mode, so the results do not establish a reliable performance difference. The `off` reports for `align` and `baseline` contain incorrect action histories. The game records are the source for the counts above.

See the [mode comparison](thinking-mode-comparison-2026-11-08.md) for elapsed times, the completed `detour` runs, and source links.

### 8 November, 15:38: detour with thinking off

Run [20261108-153803-0c67d917](../supervisor-runs/local/20261108-153803-0c67d917/) used the standard prompt and `off` mode. It reached the 60-action limit without a solution. The saved game has 14 blocked attempts, three box pushes, and no undo. The final box position was row 1, column 2. The saved rules validated the action history and final state.

The run took 368.3 seconds. Its event log has no recorded automatic retries or assistant error messages. The run did not produce a final `output/report.md`. The supervisor-owned outcome and game state remain the sources for the result. This is a second `off` sample on the same board, not evidence of a general success rate.

### 8 November, 15:51: concise prompt run

Run [20261108-155101-adef3c96](../supervisor-runs/local/20261108-155101-adef3c96/) records `high` mode and the concise prompt. The final outcome records a `length` stop after 51 of 60 actions. The game remained unsolved. The saved game records six blocked moves and 16 undo actions. The saved rules validated the final game state.

The profile task and its source workspace were removed. Sokoban is the default task, and `--task sokoban` remains valid. The standard prompt remains the default. Use `--sokoban-prompt concise` to select the separate [concise prompt](../src/sokoban/concise.prompt).

The full test suite after the removal reported **164 passed and 6 skipped**. No live model run was performed as part of that code change. The [local replay viewer](../src/run_viewer/index.html) can show saved Sokoban games.

### 8 November: DeepSeek V4.1 Flash through OpenRouter

The first pass used the standard prompt and `high` `reasoning` on all five boards. The hosted model solved `one-push`, `align`, and `detour`. It stopped before an action on `baseline` and `offset`. The `detour` solution used 26 actions, the project test's shortest path.

The additional `baseline` attempt solved the board in six actions. Two additional `offset` attempts ended with zero actions and a seven-action solution, respectively. Thus, the model solved every board at least once across eight runs. The extra attempts followed the first results and are not a balanced sample.

The saved rules validated all eight game states. The last `offset` run had one connection error and a successful automatic retry. OpenRouter provider selection and `sampling` used defaults. The remote weights and allocated context were not independently verified. These results do not isolate a model effect or establish a general success rate. See the [DeepSeek pilot report](deepseek-v4-1-flash-sokoban-2026-11-08.md).

## Current setup and hardware

The local setup uses Qwen3.5 4.2B Q4_K_M text GGUF, llama.cpp b12110, and Pi 1.4.0. It uses one 32,768-token context slot and f16 key/value cache.

The supervisor owns the game state. Each direction or undo attempt uses one action. A board view or history request uses no action. The game does not identify deadlocks or inject errors. The selected seed is random.

On the 6,144 MiB RTX 3060 Laptop GPU, the first detour run projected 3,695 MiB of GPU allocation at startup. That included 2,515 MiB for the model, 1,074 MiB for context, and 106 MiB for compute. All 33 layers were offloaded. The log reported 5,130 MiB free VRAM before model load.

The same log reported about 15.4 GiB of visible system RAM and 3.8 GiB free at startup. Its 549 MiB initial host estimate is not a peak measurement. Docker, Pi, checkpoints, and other processes also use RAM. A 64k context has not been measured.

The configured 16,384-token maximum applies to one model response. It does not give extra space to an already crowded context. Prompt, tool results, prior messages, and response tokens share the context window.

Current files: [README](../README.md), [training puzzles](../src/sokoban/puzzles-train.json), [validation puzzles](../src/sokoban/puzzles-validation.json), [test puzzles](../src/sokoban/puzzles-test.json), and [task prompt](../sokoban_workspace/task.prompt). The detour implementation and related test and documentation changes were uncommitted at this review.

## Run index

The run folders are `local`, `deepseek`, and `unclassified`. Saved records retain any historical absolute paths from the original run.

The times in each ID are local Asia/Shanghai times. For each run, use the linked directory as the primary record. `settled` means that Pi stopped. It does not mean that the task succeeded. `Not reviewed` means that this master report did not check the full task result.

### Local runs

| Run ID | Task | Recorded outcome | Task result |
| --- | --- | --- | --- |
| [20261029-191505-54dd2725](../supervisor-runs/local/20261029-191505-54dd2725/) | Profile | `loop_detected` | Not reviewed |
| [20261029-202750-a67f6c2d](../supervisor-runs/local/20261029-202750-a67f6c2d/) | Profile | `loop_detected` | Not reviewed |
| [20261030-100753-8ce2c174](../supervisor-runs/local/20261030-100753-8ce2c174/) | Profile | `settled` | Incomplete |
| [20261030-103850-af74bd43](../supervisor-runs/local/20261030-103850-af74bd43/) | Profile | `settled` | Incomplete |
| [20261105-145803-11d21add](../supervisor-runs/local/20261105-145803-11d21add/) | Profile | `settled` | Not reviewed |
| [20261105-155455-361bf887](../supervisor-runs/local/20261105-155455-361bf887/) | Sokoban | `interrupted` | Not reviewed |
| [20261105-160046-c27c951c](../supervisor-runs/local/20261105-160046-c27c951c/) | Sokoban | `settled` | Not reviewed |
| [20261105-163232-b756f090](../supervisor-runs/local/20261105-163232-b756f090/) | Sokoban | `settled` | Not reviewed |
| [20261105-164005-4185cda8](../supervisor-runs/local/20261105-164005-4185cda8/) | Sokoban | `settled` | Not reviewed |
| [20261105-164355-df30fbd4](../supervisor-runs/local/20261105-164355-df30fbd4/) | Sokoban | `settled` | Not reviewed |
| [20261105-171844-af914394](../supervisor-runs/local/20261105-171844-af914394/) | Sokoban | `settled` | Not reviewed |
| [20261105-173141-5ddd4582](../supervisor-runs/local/20261105-173141-5ddd4582/) | Sokoban | `settled` | Not reviewed |
| [20261105-173700-f3872fca](../supervisor-runs/local/20261105-173700-f3872fca/) | Sokoban | `settled` | Not reviewed |
| [20261105-190417-c9925277](../supervisor-runs/local/20261105-190417-c9925277/) | Sokoban | `settled` | Not reviewed |
| [20261105-192515-5a5a7457](../supervisor-runs/local/20261105-192515-5a5a7457/) | Sokoban | `interrupted` | Not reviewed |
| [20261107-164729-a8ca79ff](../supervisor-runs/local/20261107-164729-a8ca79ff/) | Sokoban | `action_limit` | Not solved, 24 / 24 actions |
| [20261108-120014-a4d36eb1](../supervisor-runs/local/20261108-120014-a4d36eb1/) | `one-push` | `settled` | Solved, 1 / 8 actions |
| [20261108-120124-c0006e3d](../supervisor-runs/local/20261108-120124-c0006e3d/) | `align` | `settled` | Solved, 2 / 12 actions |
| [20261108-121432-f7030672](../supervisor-runs/local/20261108-121432-f7030672/) | `baseline` | `settled` | Solved, 14 / 24 actions |
| [20261108-122047-dcac6e2b](../supervisor-runs/local/20261108-122047-dcac6e2b/) | `offset` | `settled` | Solved, 7 / 28 actions |
| [20261108-123447-a37f87be](../supervisor-runs/local/20261108-123447-a37f87be/) | `detour` | `settled`, `length` | In progress, 47 / 60 actions |
| [20261108-124837-1d1c0ba1](../supervisor-runs/local/20261108-124837-1d1c0ba1/) | `detour` | `settled`, `length` | In progress, 35 / 60 actions |
| [20261108-130242-c00fe132](../supervisor-runs/local/20261108-130242-c00fe132/) | `detour`, `off` | `action_limit` | Not solved, 60 / 60 actions |
| [20261108-134744-f3894b70](../supervisor-runs/local/20261108-134744-f3894b70/) | `one-push`, `off` | `settled` | Solved, 1 / 8 actions |
| [20261108-134938-f4c0baa7](../supervisor-runs/local/20261108-134938-f4c0baa7/) | `align`, `off` | `settled` | Solved, 6 / 12 actions |
| [20261108-135308-ba735ebf](../supervisor-runs/local/20261108-135308-ba735ebf/) | `baseline`, `off` | `settled` | Solved, 14 / 24 actions |
| [20261108-153803-0c67d917](../supervisor-runs/local/20261108-153803-0c67d917/) | `detour`, `off`, standard | `action_limit` | Not solved, 60 / 60 actions |
| [20261108-155101-adef3c96](../supervisor-runs/local/20261108-155101-adef3c96/) | `detour`, `high`, concise | `settled`, `length` | In progress, 51 / 60 actions |

### Unclassified run

| Run ID | Task | Recorded outcome | Task result |
| --- | --- | --- | --- |
| [20261107-151309-8be6394e](../supervisor-runs/unclassified/20261107-151309-8be6394e/) | Sokoban | No outcome record | Unknown |

### DeepSeek runs

| Run ID | Task | Recorded outcome | Task result |
| --- | --- | --- | --- |
| [20261108-162351-3ade31c6](../supervisor-runs/deepseek/20261108-162351-3ade31c6/) | `one-push`, OpenRouter, `high` | `settled` | Solved, 1 / 8 actions |
| [20261108-162444-3714bbfb](../supervisor-runs/deepseek/20261108-162444-3714bbfb/) | `align`, OpenRouter, `high` | `settled` | Solved, 2 / 12 actions |
| [20261108-162506-3b01a920](../supervisor-runs/deepseek/20261108-162506-3b01a920/) | `baseline`, OpenRouter, `high` | `settled` | In progress, 0 / 24 actions |
| [20261108-162521-fec162dc](../supervisor-runs/deepseek/20261108-162521-fec162dc/) | `offset`, OpenRouter, `high` | `settled` | In progress, 0 / 28 actions |
| [20261108-162534-99557fb5](../supervisor-runs/deepseek/20261108-162534-99557fb5/) | `detour`, OpenRouter, `high` | `settled` | Solved, 26 / 60 actions |
| [20261108-162730-7ac8057a](../supervisor-runs/deepseek/20261108-162730-7ac8057a/) | `baseline`, OpenRouter, `high`, extra attempt | `settled` | Solved, 6 / 24 actions |
| [20261108-162801-b56857a6](../supervisor-runs/deepseek/20261108-162801-b56857a6/) | `offset`, OpenRouter, `high`, extra attempt | `settled` | In progress, 0 / 28 actions |
| [20261108-162838-0c3c7003](../supervisor-runs/deepseek/20261108-162838-0c3c7003/) | `offset`, OpenRouter, `high`, extra attempt | `settled` | Solved, 7 / 28 actions |

## Video report

The [project report video](../outputs/report-video-20261108/long-horizon-project-report.mp4) summarizes the project through 8 November. Its narration uses LFM3 Omni 2B through the local llama.cpp runtime. The [narration text](../outputs/report-video-20261108/narration.md) is available with the video. The video is a summary of the records, not an additional experiment.

## Next research steps

1. Review the unclassified 5 November runs if their results are needed. Record the evidence and limits for each result.
2. Establish repeated baselines on several distinct boards. Record solve rate, actions, blocked moves, deadlocks, recovery, and stop reason.
3. Test shorter per-action instructions as a separate condition. Keep the full board and one action per command for the first comparison.
4. Define recovery cases and a delayed-feedback condition. Verify that a solution exists within each action budget.
5. Reserve unseen boards for evaluation. Keep their data separate from trajectories used to train the model.
6. Select a `post-training` method only after the baseline and data support the choice of method. Record changes to the model, backend, prompt, context, and sample settings.

## How to add future reports

When a new experiment report is completed, add its date, conditions, results, evidence limits, and link to this master report. Add each new run to the run index. Update the current state and next steps if the new evidence changes them. Keep the detailed report and raw records. Mark unfinished or unreviewed runs as such. Keep results from different conditions separate.

Run directories are local, and Git can exclude them. Preserve them if later analysis needs the raw records. Some older temporary Pi traces and artifact folders are no longer available. Their reports identify those gaps.
