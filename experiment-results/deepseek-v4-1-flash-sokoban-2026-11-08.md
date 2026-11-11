# DeepSeek V4.1 Flash Sokoban pilot

Date: 8 November 2026, Asia/Shanghai (UTC+8).

## Scope and conditions

The supervisor ran the five Sokoban boards with `deepseek/deepseek-v4.1-flash-1017` through OpenRouter and Pi. Each run used the standard prompt, `high` `reasoning` effort, and a 2,700-second task limit. The action limits were the same as the local pilot. The supervisor owned the game state and stopped the agent at the action limit.

Pi used a configured context of 1,048,576 tokens and a response limit of 16,384 tokens. OpenRouter used default provider selection and `sampling`. The records do not verify the remote provider, weights, context allocation, or effective `sampling` values. Pi's custom model entry has zero price data. Its cost field is not an invoice.

The first pass used one run on each board. After the `baseline` and `offset` runs stopped before an action, we added one attempt on each board. The second `offset` attempt also stopped before an action, so we added one final `offset` attempt. These extra attempts were selected after the first results. This is not a balanced sample.

## Results

| Board | Attempt | Result | Actions / limit | Time | Run |
| --- | ---: | --- | ---: | ---: | --- |
| `one-push` | 1 | Solved | 1 / 8 | 10.6 s | [16:23](../supervisor-runs/deepseek/20261108-162351-3ade31c6/) |
| `align` | 1 | Solved | 2 / 12 | 11.3 s | [16:24](../supervisor-runs/deepseek/20261108-162444-3714bbfb/) |
| `baseline` | 1 | In progress when agent stopped | 0 / 24 | 7.0 s | [16:25](../supervisor-runs/deepseek/20261108-162506-3b01a920/) |
| `offset` | 1 | In progress when agent stopped | 0 / 28 | 5.5 s | [16:25](../supervisor-runs/deepseek/20261108-162521-fec162dc/) |
| `detour` | 1 | Solved | 26 / 60 | 74.6 s | [16:25](../supervisor-runs/deepseek/20261108-162534-99557fb5/) |
| `baseline` | 2 | Solved | 6 / 24 | 23.1 s | [16:27](../supervisor-runs/deepseek/20261108-162730-7ac8057a/) |
| `offset` | 2 | In progress when agent stopped | 0 / 28 | 5.0 s | [16:28](../supervisor-runs/deepseek/20261108-162801-b56857a6/) |
| `offset` | 3 | Solved | 7 / 28 | 48.6 s | [16:28](../supervisor-runs/deepseek/20261108-162838-0c3c7003/) |

All eight supervisor outcomes were `settled`. That status alone does not mean that a board was solved. The supervisor-owned game records show five solved runs and three unfinished runs. The model solved each of the five boards at least once. No run recorded a blocked move or an undo.

In each unfinished run, the agent displayed the board and wrote a proposed action. It then ended without a tool call to execute that action. It did not write a final report file. The records do not establish why it stopped.

The solved `detour` run used 26 actions. The project test uses breadth-first search and gives 26 as the shortest solution for this board. The agent moved the box down, away from the goal, before it moved the box toward the goal. The event record shows game commands and a report write.

The last `offset` run had one `Connection error.` The automatic retry succeeded, and the run solved the board. The other seven runs did not record an automatic retry. The records do not establish the cause of the connection error.

## Comparison and limits

The five first-pass boards and saved prompts match the earlier `high` local runs on the same boards. DeepSeek solved three boards on the first pass. The local model solved four and did not solve `detour` in the cited runs. The later DeepSeek attempts solved `baseline` and `offset`.

The hosted model, backend, configured context, `sampling`, and image differ from the local condition. The `high` `reasoning` mode also differs. These observations do not isolate a model effect. The sample is small, the extra attempts were outcome-selected, and the boards are not a validated difficulty scale. The elapsed times include agent and report work and do not measure inference speed alone.

## Verification

The saved rules replayed and validated all eight game states. The five first-pass puzzle definitions and task prompts matched their earlier local `high` counterparts. The saved game record is the source for each outcome and action count. The project suite reported 167 passed and 6 skipped before these runs. The skipped tests were optional integration checks.

See the [master report](experiment-summary.md) for the run index and earlier project results.
