# Specification: Sokoban action limit and board display

Status: Implemented

Scope: The existing one-box Sokoban pilot

## Objective

Bound play in a Sokoban run, make the board easier to interpret, and make exploration and recovery measurable. The agent must see the current board and coordinates, the remaining budget, and whether it solved the puzzle or ran out of actions. Preserve the existing profile task and supervisor behavior.

## Assumptions

- The current puzzle has a 24-action limit. This is a pilot value, not an experimentally validated threshold.
- The shortest solution to the current board takes six moves. The previously discussed four-times-shortest rule motivates the pilot limit; it is not an automatic rule for future puzzles.
- Future puzzles may have different limits, but creating, generating, selecting, or solving multiple puzzles is outside this change.
- The Sokoban run directory is output/, as specified by its current AGENTS.md. Each supervised run receives its own workspace copy.

## Action and budget rules

1. An action is one invocation of up, down, left, right, or undo against an initialized, nonterminal game. Each consumes exactly one action:
   - A successful move or push.
   - A blocked direction attempt, even though the board does not change.
   - A successful undo or an undo attempt when there is nothing to undo.
2. Init and show do not consume actions. Commands rejected by argument parsing or unable to load a valid state do not consume actions. A counted action is saved before the command reports its result.
3. A new game begins with 24 actions remaining. The agent sees the total limit, used count, remaining count, board, and game outcome after initialization, after every action, and on show.
4. Append each counted action once to the persisted action history with its action and result. The used count must agree with the action history; undo changes board history but does not erase or refund action history.
5. After a counted action, check for a solved board first. If solved on the 24th action, the outcome is solved. Otherwise, when the 24th action has been consumed, the outcome is action_limit_reached. Before either terminal outcome, the outcome is in_progress.
6. Both solved and action_limit_reached are terminal. Further direction and undo commands report the terminal outcome and leave the board, histories, and counts unchanged. Show remains available and does not change the state.
7. Init must keep its current no-overwrite behavior. The task instructions tell the agent not to create a second state file, restart the game, edit the state directly, or change the game program to bypass the limit.

## Board representation

- On init, show, and every action, display the current board as a grid with a column-number header, a row number beside each row, and exactly one space between cell symbols. Display empty floor as `-` rather than an invisible space.
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

- Save the limit in game.json at initialization. A running game's limit must not change if the default in the program changes later.
- Use the persisted action history to determine how many actions have been used. Retain enough existing board history to support undo.
- A missing, unreadable, malformed, or incompatible state must produce a clear error without replacing the existing file or silently resetting the budget. A pre-feature state without a saved limit is incompatible; do not silently assign it a new budget.
- The state file and program remain inside the agent-writable workspace. The limit is enforced by the game interface for cooperative use, not as a tamper-proof security boundary. Retain supervisor event logs for auditing tool calls.

## Agent instructions and outcome reporting

- Update sokoban_workspace/task.prompt with the action-count rules, the 24-action limit, terminal behavior, and instructions to report the result without claiming success when the limit is reached.
- Align the prompt examples with sokoban_workspace/AGENTS.md: the game state and report go under output/. Do not restore versioned output directories.
- On solved or action_limit_reached, the agent should stop playing and write output/report.md with the game outcome, actions used, remaining actions, and a brief account of blocked moves and undos.
- A supervisor timeout can interrupt the agent before it writes a report. In that case, preserve whatever state and event records exist; do not claim that a report or game outcome was produced.
- Keep game outcome distinct from supervisor outcome: settled means Pi stopped and does not prove puzzle success; timeout is a wall-clock termination. A game can have been solved before a later supervisor timeout.
- Update the project README to describe the action limit and these distinctions without implying that the supervisor validates puzzle success.

## Existing interfaces and scope

- sokoban_workspace/src/sokoban.py: enforce and persist the budget; display the board, labeled coordinates, remaining actions, and game outcome.
- sokoban_workspace/task.prompt and, only if needed, sokoban_workspace/AGENTS.md: provide consistent game and output instructions.
- tests/test_sokoban.py: exercise the game through its command-line interface and persisted state.
- tests/test_container.py: update the existing Sokoban copy test, which still expects run-version and .run-version after the workspace was changed to use output/. Verify that copied instructions and prompt agree.
- README.md: document the pilot limit, board display, and current output instructions.
- No new dependencies, new boards, solver, deadlock detection, injected errors, automatic per-difficulty scaling, or supervisor outcome changes.

## Examples

The existing CLI is used as follows; the output/ directory must already exist:

    python3 src/sokoban.py --state output/game.json init
    python3 src/sokoban.py --state output/game.json up
    python3 src/sokoban.py --state output/game.json show

After init, the game reports 0 used and 24 remaining. After up, it reports 1 used and 23 remaining. The subsequent show still reports 1 used and 23 remaining. Exact display wording is an implementation choice; the numbers and outcome must be unambiguous.

## Verification and acceptance criteria

Use Python 3.12 and pytest, following the existing four-space indentation, snake_case, and public-interface type-annotation conventions.

- Run uv run pytest from the project root.
- Test a fresh game's limit, persisted count, and display; verify that show does not consume an action.
- Verify that the displayed grid includes row and column labels, visible floor cells, and the correct wall layout, player, box, and goal positions on initialization and after movement.
- Verify that position labels use row/column order and zero-based indices, match the displayed grid and saved `(x, y)` state, and remain correct for `+` and `*`.
- Verify that a blocked action and an undo show the unchanged or restored board and coordinates respectively, and that terminal action attempts report the existing terminal state without changing it.
- Test a valid move, blocked move, successful undo, and empty-history undo; each consumes exactly one action and records its result.
- Verify that undo restores the board without refunding or deleting earlier actions.
- Verify that an unsolved game reaches action_limit_reached on action 24, and a game solved on action 24 reports solved.
- Verify that later action attempts cannot mutate either terminal state, and show still works.
- Verify that init cannot overwrite an existing file, and invalid or pre-feature state is rejected without modifying it.
- Verify that the copied Sokoban workspace includes matching output instructions, and the profile task and supervisor tests continue to pass.
- Keep the existing checks for board movement and solving, adapting the old test where terminal behavior changes.

## Boundaries

Always preserve the existing profile task, validate state before changing it, and keep the action budget separate from the supervisor's wall-clock limit. Never commit secrets or local environment files. Changes to dependencies, additional puzzle variants, or supervisor termination behavior require a separate scope decision.
