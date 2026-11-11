import copy
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sokoban_authority import SokobanAuthority, load_puzzle


@pytest.mark.parametrize(
    ("puzzle_id", "limit", "solution"),
    [
        ("one-push", 8, "up"),
        ("align", 12, "right up"),
        ("baseline", 24, "left down down right up up"),
        ("offset", 28, "up up left up right right right"),
        ("detour", 60, "up left left left up left left down down down down right down down left left up right right right down right up up up up"),
    ],
)
def test_puzzles_solve_with_shortest_paths_and_replay(tmp_path: Path, puzzle_id: str, limit: int, solution: str) -> None:
    puzzle = load_puzzle(puzzle_id)
    board = puzzle["board"]
    assert len({len(row) for row in board}) == 1
    assert all(c == "#" for c in board[0] + board[-1])
    assert all(row[0] == row[-1] == "#" for row in board)
    assert all(sum(row.count(c) for row in board) == 1 for c in "@$." )
    game = SokobanAuthority(tmp_path, puzzle_id=puzzle_id)
    assert json.loads((tmp_path / "puzzle.json").read_text()) == puzzle
    assert f"Actions: 0 / {limit}" in game.execute("show")
    queue = deque([(game.rules.initial_state(), 0)])
    visited = set()
    shortest = None
    while queue:
        state, depth = queue.popleft()
        key = (tuple(state["player"]), tuple(state["box"]))
        if key in visited:
            continue
        visited.add(key)
        if game.rules.outcome(state) == "solved":
            shortest = depth
            break
        for direction in game.rules.DIRECTIONS:
            next_state = copy.deepcopy(state)
            if game.rules.play(next_state, direction) == "Moved.":
                queue.append((next_state, depth + 1))
    assert shortest == len(solution.split())
    for direction in solution.split():
        game.execute(direction)
    assert game.summary() == {"outcome": "solved", "actions": shortest, "limit": limit}
    replay = subprocess.run([sys.executable, str(tmp_path / "sokoban_rules.py"), "--state", str(game.path), "show"], capture_output=True, text=True, check=True)
    assert replay.stdout.rstrip() == game.execute("show")


@pytest.mark.parametrize("puzzle_id", ["one-push", "align", "baseline", "offset", "detour"])
def test_selected_budget_counts_blocked_and_undo_actions(tmp_path: Path, puzzle_id: str) -> None:
    game = SokobanAuthority(tmp_path, puzzle_id=puzzle_id)
    limit = game.state["action_limit"]
    for _ in range(limit):
        game.execute("undo")
    assert game.limit_reached.is_set()
    assert game.summary() == {"outcome": "action_limit_reached", "actions": limit, "limit": limit}


@pytest.mark.parametrize("puzzle_id,solution", [("one-push", "up"), ("align", "right up"), ("baseline", "left down down right up up"), ("offset", "up up left up right right right"), ("detour", "up left left left up left left down down down down right down down left left up right right right down right up up up up")])
def test_solution_on_last_action_is_still_solved(tmp_path: Path, puzzle_id: str, solution: str) -> None:
    game = SokobanAuthority(tmp_path, puzzle_id=puzzle_id)
    actions = solution.split()
    for _ in range(game.state["action_limit"] - len(actions)):
        game.execute("undo")
    for action in actions:
        game.execute(action)
    assert game.limit_reached.is_set()
    assert game.summary()["outcome"] == "solved"


def test_profile_task_is_no_longer_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    import supervisor
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--task", "profile", "--llama-server", "x", "--model-file", "y"])
    with pytest.raises(SystemExit) as error:
        supervisor.main()
    assert error.value.code == 2
