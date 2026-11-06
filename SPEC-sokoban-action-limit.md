# Specification: Sokoban action limit and board display

Status: Implemented

Scope: The existing one-box Sokoban pilot

## Objective

Bound play in a Sokoban run, make the board easier to interpret, and make exploration and recovery measurable. The agent must see the current board and coordinates, the remaining budget, and whether it solved the puzzle or ran out of actions. Preserve the existing profile task and supervisor behavior.

## Assumptions

- The current puzzle has a 24-action limit. This is a pilot value, not an experimentally validated threshold.
- The shortest solution to the current board takes six moves. The previously discussed four-times-shortest rule motivates the pilot limit; it is not an automatic rule for future puzzles.
- Future puzzles may have different limits, but creating, generating, selecting, or solving multiple puzzles is outside this change.
- The supervisor creates an empty output/ directory inside each Sokoban run's workspace copy before the model starts. If the copied workspace already contains output/, preparation stops without overwriting it.

## Action and budget rules

1. An action is one invocation of up, down, left, right, or undo against an initialized, nonterminal game. Each consumes exactly one action:
   - A successful move or push.
   - A blocked direction attempt, even though the board does not change.
   - A successful undo or an undo attempt when there is nothing to undo.
2. The supervisor initializes the game before the agent starts. Show and history do not consume actions. Invalid requests do not consume actions. A counted action is saved before the command reports its result.
3. A new game begins with 24 actions remaining. The agent sees the total limit, used count, remaining count, board, and game outcome on show and after each action whose response is delivered. The 24th response may be interrupted by immediate shutdown.
4. Append each counted action once to the persisted action history with its action and result. The used count must agree with the action history; undo changes board history but does not erase or refund action history.
5. After a counted action, check for a solved board first. If solved on the 24th action, the outcome is solved. Otherwise, when the 24th action has been consumed, the outcome is action_limit_reached. Before either terminal outcome, the outcome is in_progress.
6. Both solved and action_limit_reached are terminal. Further direction and undo commands do not change the state. After action 24, the supervisor immediately terminates the agent and records supervisor status action_limit, including when the game outcome is solved.
7. The agent can request show, history, or one direction or undo action through the controlled game client. The interface has no initialize or reset action.

## Board representation

- On show and every delivered action response, display the current board as a grid with a column-number header, a row number beside each row, and exactly one space between cell symbols. Display empty floor as `-` rather than an invisible space.
- Keep the other Sokoban symbols: `#` for a wall, `.` for an empty goal, `@` for the player, `$` for the box, `+` for the player on the goal, and `*` for the box on the goal. The goal and wall layout must come from the game board, not a separate hand-maintained description.
- After the grid, show the current player, box, and goal positions with explicit `row` and `column` labels. Use zero-based indices: row 0 is the top row, column 0 is the leftmost column, up decreases row, and right increases column. The existing game stores positions as `(x, y)`; display column from `x` and row from `y` without changing the saved coordinate convention.
- The grid, the coordinates, and the actual game state must agree, including when the player or box is on the goal. The coordinates for the goal remain visible when `+` or `*` occupies it. Do not add a separately maintained wall-coordinate list.
- Show the same information after successful, blocked, and undo actions, as well as when an action is rejected because the game is terminal. It must reflect the resulting board rather than the attempted move.
- Update the task prompt to explain the symbols, the row and column indexing, movement directions, and that each `#` cell is a wall. It should direct the agent to the displayed board for the current wall locations and explain that walls cannot be crossed or pushed through. Do not hard-code a separate board layout or path to the goal in the prompt.
- This change combines visible floor cells, grid labels, and the coordinate summary in one display condition. It also introduces an action limit that the recorded baseline did not have. Compare runs as combined conditions; do not claim that one individual element caused any improvement.
- Do not include legal-action lists, suggested moves, deadlock warnings, or computed solution hints in the display. They would add assistance beyond the current game state.

For the current starting board, the display must contain the following grid and coordinates:

```text
    0 1 2 3 4 5 6
0   # # # # # # #
1   # - - . - - #
2   # - - @ - - #
3   # - - $ - - #
4   # - - - - - #
5   # - - - - - #
6   # # # # # # #

Player: row 2, column 3
Box: row 3, column 3
Goal: row 1, column 3
```

## Persistence and failure behavior

- The supervisor owns the game state, limit, and action history in memory and writes game.json directly in its run record directory, outside the agent-writable workspace. A running game's limit must not change if the default changes later.
- Save the exact copied Sokoban source, including the board and rules, as sokoban_rules.py in the run record directory and load the authoritative game from it. Remove the source from the agent workspace after saving it. Keep the snapshot so old game records remain verifiable after the project changes; never overwrite an existing snapshot.
- Save the full state atomically before acknowledging a counted action. A save or game-service failure stops the run instead of silently resetting the budget. Retain enough board history to support undo and preserve supervisor event logs for auditing.
- The agent cannot reset the authoritative state by deleting or changing files in its workspace. The game interface has no reset operation. A separately constructed fake game in the workspace has no effect on the authoritative outcome.

## Agent instructions and outcome reporting

- Update sokoban_workspace/task.prompt with the action-count rules, the 24-action limit, terminal behavior, and instructions to report the result without claiming success when the limit is reached.
- Tell the agent in task.prompt that output/ already exists for its report. The supervisor creates and owns the game state outside the workspace. Do not restore versioned output directories.
- On solved before action 24, the agent should stop playing and write output/report.md with the game outcome, actions used, remaining actions, and a brief account of blocked moves and undos. At action 24 the supervisor stops the agent immediately, so no agent-written report is guaranteed.
- A supervisor timeout can interrupt the agent before it writes a report. In that case, preserve whatever state and event records exist; do not claim that a report or game outcome was produced.
- Keep game outcome distinct from supervisor outcome: settled means Pi stopped and does not prove puzzle success; timeout is a wall-clock termination. A game can have been solved before a later supervisor timeout.
- Record the authoritative game outcome and action count in the supervisor outcome separately from the supervisor termination status.
- On every shutdown path, wait for an action already being saved and freeze the game before recording the final outcome. Later requests cannot change it. If that final action reaches the limit, record action_limit and perform the immediate container stop.

## Existing interfaces and scope

- src/sokoban_authority.py: own and persist the game and action limit outside the agent workspace, using the existing Sokoban rules.
- src/supervisor.py, src/network_guard.py, and docker/gateway.py: relay controlled game actions and stop the agent on action 24.
- sokoban_workspace/src/play.py: submit a single action or request the current board and history.
- sokoban_workspace/task.prompt: provide the game, environment, and output instructions without requiring an AGENTS.md file.
- tests/test_sokoban.py: exercise the game through its command-line interface and persisted state.
- tests/test_container.py: update the existing Sokoban copy test, which still expects run-version and .run-version after the workspace was changed to use output/. Verify that copied instructions and prompt agree.
- README.md: document the pilot limit, board display, and current output instructions.
- No new dependencies, new boards, solver, deadlock detection, injected errors, or automatic per-difficulty scaling.

## Examples

The agent CLI is used as follows inside a supervised run:

    python3 src/play.py show
    python3 src/play.py up
    python3 src/play.py show

The first show reports 0 used and 24 remaining. After up, the game reports 1 used and 23 remaining. The subsequent show still reports 1 used and 23 remaining. Exact display wording is an implementation choice; the numbers and outcome must be unambiguous.

## Verification and acceptance criteria

Use Python 3.12 and pytest, following the existing four-space indentation, snake_case, and public-interface type-annotation conventions.

- Run uv run pytest from the project root.
- Test a fresh game's limit, persisted count, and display; verify that show does not consume an action.
- Verify that the displayed grid includes row and column labels, visible floor cells, and the correct wall layout, player, box, and goal positions on the first show and after movement.
- Verify that position labels use row/column order and zero-based indices, match the displayed grid and saved `(x, y)` state, and remain correct for `+` and `*`.
- Verify that a blocked action and an undo show the unchanged or restored board and coordinates respectively, and that terminal action attempts report the existing terminal state without changing it.
- Test a valid move, blocked move, successful undo, and empty-history undo; each consumes exactly one action and records its result.
- Verify that undo restores the board without refunding or deleting earlier actions.
- Verify that an unsolved game reaches action_limit_reached on action 24, and a game solved on action 24 reports solved.
- Verify that later action attempts cannot mutate either terminal state, and show still works.
- Verify that the agent cannot initialize or reset the authoritative state, including after changing its workspace, and that save failures do not erase recorded actions.
- Verify that the agent is stopped immediately after action 24 and the supervisor records both the action count and the game outcome, including a solution on action 24.
- Verify that the copied Sokoban workspace includes matching output instructions, and the profile task and supervisor tests continue to pass.
- Keep the existing checks for board movement and solving, adapting the old test where terminal behavior changes.

## Boundaries

Always preserve the existing profile task, validate requests before changing state, and keep the action budget separate from the supervisor's wall-clock limit. Never commit secrets or local environment files. Changes to dependencies or additional puzzle variants require a separate scope decision.
