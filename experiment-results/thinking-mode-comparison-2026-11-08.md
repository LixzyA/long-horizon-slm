# Sokoban comparison: `high` and `off` modes

Review date: 8 November 2026, approximately 15:53, Asia/Shanghai (UTC+8).

## Scope and conditions

This report compares the retained Qwen3.5 Sokoban runs in `high` and `off` modes. It uses supervisor-owned game records for outcomes and action counts. Each easy board has one run per mode. The `detour` board has two completed standard-prompt runs in each mode. These samples do not establish which mode is better.

For each easy-board pair, the saved board and task prompt are identical. The model hash, llama.cpp executable hash and version, container image, context, cache type, and sample settings also match. The seed is random, so the pairs do not use a fixed matched seed. Each task had a 2,700-second time limit.

`High` enables the model template's `thinking` mode. `Off` disables it. An `off` run can still contain natural-language explanations. Elapsed time includes agent work and reports after a solution. It is not a direct measure of model inference speed.

## Matched easy boards

Each cell represents one run. The table gives the action and undo counts from the game records and the elapsed task time.

| Board | Action limit | `high`: result, actions, undo, time | `off`: result, actions, undo, time |
| --- | ---: | --- | --- |
| `one-push` | 8 | Solved, 1 action, 0 undo, 22.9 s | Solved, 1 action, 0 undo, 34.8 s |
| `align` | 12 | Solved, 2 actions, 0 undo, 39.6 s | Solved, 6 actions, 1 undo, 104.5 s |
| `baseline` | 24 | Solved, 14 actions, 3 undo, 149.8 s | Solved, 14 actions, 3 undo, 198.8 s |

None of these six runs had a blocked direction attempt. All six solved their boards. The three `off` runs took more elapsed time in this sample. The sample is too small to infer a speed or quality difference.

On `align`, the `off` run pushed the box right on action 2. It used undo on action 3, then solved on action 6. The `high` run solved in two actions without undo. On `baseline`, both runs used three undos and solved in 14 actions. Their action sequences were different.

The model's `off` report for `align` incorrectly says that no undo was needed. Its `baseline` report lists only nine actions despite the correct total of 14. The game records contain the full sequences. This is a report accuracy issue, not evidence that the game failed.

## Harder board: `detour`

| Mode | Run | Final game state | Actions / limit | Blocked | Undo attempts | Time |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `high` | [12:34](../supervisor-runs/local/20261108-123447-a37f87be/) | Unsolved; agent stopped with `length` | 47 / 60 | 11 | 2 | 429.0 s |
| `high` | [12:48](../supervisor-runs/local/20261108-124837-1d1c0ba1/) | Unsolved; agent stopped with `length` | 35 / 60 | 7 | 4 | 478.2 s |
| `off` | [13:02](../supervisor-runs/local/20261108-130242-c00fe132/) | Unsolved; action limit reached | 60 / 60 | 24 | 0 | 229.5 s |
| `off` | [15:38](../supervisor-runs/local/20261108-153803-0c67d917/) | Unsolved; action limit reached | 60 / 60 | 14 | 0 | 368.3 s |

The second `high` run had three successful undo actions and one empty undo. Both `high` runs pushed the box to the top row and continued without a solution. The first `off` run did not move the box. It entered a two-square movement loop and used all 60 actions. The second `off` run pushed the box three times to the top row and also used all 60 actions.

The two stop conditions are different. The `high` runs ended with `length` before the action limit. Both `off` runs reached the action limit.

Five gateway requests in the first `off` run received a 503 response and succeeded on retry. Its movement loop started before the first 503. The records do not establish why those errors occurred. The second `off` run had no recorded automatic retries or assistant error messages.

Two runs per mode do not support a reliable mode comparison on this board. The context limit also makes action counts hard to compare as a measure of task capability. See the [13:02 trace report](experiment-20261108-130242.md) and the [master report](experiment-summary.md).

## Evidence

- `one-push`: [high](../supervisor-runs/local/20261108-120014-a4d36eb1/), [off](../supervisor-runs/local/20261108-134744-f3894b70/).
- `align`: [high](../supervisor-runs/local/20261108-120124-c0006e3d/), [off](../supervisor-runs/local/20261108-134938-f4c0baa7/).
- `baseline`: [high](../supervisor-runs/local/20261108-121432-f7030672/), [off](../supervisor-runs/local/20261108-135308-ba735ebf/).
- `offset`: one [high run](../supervisor-runs/local/20261108-122047-dcac6e2b/) solved in seven actions. No retained `off` run was available at this review.

The saved Sokoban rules replayed and validated the game states for the six easy-board runs and both `off` detour runs. The earlier report records the two `high` detour outcomes. More runs per condition and more distinct boards are needed before a comparison can support a general conclusion.
