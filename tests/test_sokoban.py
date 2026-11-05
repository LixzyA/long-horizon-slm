import json
import subprocess
import sys
from pathlib import Path


GAME = Path(__file__).resolve().parents[1] / "sokoban_workspace" / "src" / "sokoban.py"


def test_play_blocked_undo_and_solve(tmp_path: Path) -> None:
    state = tmp_path / "game.json"

    def run(action: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GAME), "--state", str(state), action],
            capture_output=True,
            text=True,
            check=True,
        )

    assert "Not solved." in run("init").stdout
    assert "Moved." in run("up").stdout
    assert "Blocked" in run("up").stdout
    assert "Move undone." in run("undo").stdout
    assert "Nothing to undo" in run("undo").stdout
    assert "Moved." in run("left").stdout
    assert "Move undone." in run("undo").stdout
    for action in ("left", "down", "down", "right", "up", "up"):
        result = run(action)
    assert "Solved!" in result.stdout
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert len(saved["actions"]) == 12
    assert saved["box"] == [3, 1]
    assert "Not solved." in run("undo").stdout
    repeated_init = subprocess.run(
        [sys.executable, str(GAME), "--state", str(state), "init"],
        capture_output=True,
        text=True,
    )
    assert repeated_init.returncode != 0
    assert json.loads(state.read_text(encoding="utf-8"))["box"] == [3, 2]
