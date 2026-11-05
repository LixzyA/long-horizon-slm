import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1] / "sokoban_workspace" / "src" / "sokoban.py"


@pytest.fixture
def game(tmp_path: Path):
    state = tmp_path / "game.json"

    def run(action: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GAME), "--state", str(state), action],
            capture_output=True,
            text=True,
            check=check,
        )

    return state, run


def test_board_positions_blocked_undo_and_solved(game) -> None:
    state, run = game
    initial = run("init").stdout
    assert "    0 1 2 3 4 5 6\n" in initial
    assert "1   # - - . - - #\n2   # - - @ - - #\n3   # - - $ - - #" in initial
    assert "Player: row 2, column 3" in initial
    assert "Box: row 3, column 3" in initial
    assert "Goal: row 1, column 3" in initial
    assert "Actions: 0 / 24" in initial and "Remaining: 24" in initial
    assert "in_progress" in initial
    assert "Actions: 0 / 24" in run("show").stdout

    up = run("up").stdout
    assert "1   # - - + - - #" in up
    assert "Player: row 1, column 3" in up
    assert "Goal: row 1, column 3" in up
    blocked = run("up").stdout
    assert "Blocked" in blocked and "Player: row 1, column 3" in blocked
    assert "1   # - - + - - #" in blocked
    assert "Actions: 2 / 24" in blocked and "Outcome: in_progress" in blocked
    undone = run("undo").stdout
    assert "Move undone." in undone and "Player: row 2, column 3" in undone
    assert "2   # - - @ - - #" in undone
    assert "Actions: 3 / 24" in undone and "Outcome: in_progress" in undone
    assert "Nothing to undo." in run("undo").stdout
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["player"] == [3, 2] and len(saved["actions"]) == 4
    assert saved["history"] == []

    for action in ("left", "down", "down", "right", "up", "up"):
        result = run(action)
    assert "1   # - - * - - #" in result.stdout
    assert "Box: row 1, column 3" in result.stdout
    assert "Goal: row 1, column 3" in result.stdout
    assert "solved" in result.stdout.lower()
    before = state.read_bytes()
    terminal = run("undo").stdout
    assert "solved" in terminal.lower() and "1   # - - * - - #" in terminal
    assert "Box: row 1, column 3" in terminal and "Actions: 10 / 24" in terminal
    assert state.read_bytes() == before
    assert "solved" in run("show").stdout.lower()
    assert run("init", check=False).returncode != 0
    assert state.read_bytes() == before


def test_exhaustion_counts_attempts_and_keeps_terminal_state(game) -> None:
    state, run = game
    run("init")
    for _ in range(24):
        result = run("undo")
    assert "Actions: 24 / 24" in result.stdout
    assert "Remaining: 0" in result.stdout
    assert "action_limit_reached" in result.stdout
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert len(saved["actions"]) == 24 and saved["history"] == []
    before = state.read_bytes()
    assert "action_limit_reached" in run("left").stdout
    assert "action_limit_reached" in run("show").stdout
    assert state.read_bytes() == before


def test_solving_on_final_action_takes_precedence(game) -> None:
    state, run = game
    run("init")
    for _ in range(18):
        run("undo")
    for action in ("left", "down", "down", "right", "up"):
        run(action)
    assert "in_progress" in run("show").stdout
    result = run("up")
    assert "Outcome: solved" in result.stdout
    assert "Actions: 24 / 24" in result.stdout
    assert json.loads(state.read_text(encoding="utf-8"))["box"] == [3, 1]


@pytest.mark.parametrize("contents", ["not json", "{}", '{"action_limit": 24, "actions": []}'])
def test_invalid_or_old_state_is_not_replaced(game, contents: str) -> None:
    state, run = game
    state.write_text(contents, encoding="utf-8")
    result = run("left", check=False)
    assert result.returncode != 0
    assert "state" in result.stderr.lower()
    assert state.read_text(encoding="utf-8") == contents


def test_persisted_limit_is_used_and_invalid_history_rejected(game) -> None:
    state, run = game
    run("init")
    saved = json.loads(state.read_text(encoding="utf-8"))
    saved["action_limit"] = 2
    state.write_text(json.dumps(saved), encoding="utf-8")
    assert "Remaining: 2" in run("show").stdout
    run("undo")
    assert "action_limit_reached" in run("undo").stdout
    saved = json.loads(state.read_text(encoding="utf-8"))
    saved["player"] = [0, 0]
    state.write_text(json.dumps(saved), encoding="utf-8")
    before = state.read_bytes()
    assert run("show", check=False).returncode != 0
    assert state.read_bytes() == before


def test_failed_save_preserves_game_and_cleans_temporary_file(
    game, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state, run = game
    run("init")
    before = state.read_bytes()
    spec = importlib.util.spec_from_file_location("sokoban_test", GAME)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fail_replace(source, target):
        raise OSError("disk error")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    monkeypatch.setattr(sys, "argv", [str(GAME), "--state", str(state), "left"])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 1
    assert "Moved." not in capsys.readouterr().out
    assert state.read_bytes() == before
    assert list(state.parent.iterdir()) == [state]
