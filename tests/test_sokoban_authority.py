import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sokoban_authority import GAME_PATH, SokobanAuthority


def test_authority_counts_actions_and_preserves_state_outside_workspace(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert "Remaining: 24" in game.execute("show")
    assert "Remaining: 23" in game.execute("up")
    assert "Blocked" in game.execute("up")
    assert "Remaining: 21" in game.execute("undo")
    (workspace / "game.json").write_text("{}", encoding="utf-8")
    assert "Actions: 3 / 24" in game.execute("show")
    saved = json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))
    assert [a["action"] for a in saved["actions"]] == ["up", "up", "undo"]
    assert not game.limit_reached.is_set()


def test_limit_is_global_and_terminal_even_for_concurrent_calls(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(game.execute, ["undo"] * 40))
    saved = json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))
    assert len(saved["actions"]) == 24
    assert game.limit_reached.is_set()
    assert sum("Nothing to undo." in result for result in results) == 24
    assert "Remaining: 0" in game.execute("show")
    with pytest.raises(ValueError):
        game.execute("init")
    history = json.loads(game.execute("history"))
    assert len(history["actions"]) == 24 and history["remaining"] == 0
    assert history["actions_used"] == 24 and history["coordinate_order"] == ["column", "row"]


def test_solved_on_final_action_is_recorded_before_limit_notification(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    for _ in range(18):
        game.execute("undo")
    for action in ("left", "down", "down", "right", "up", "up"):
        result = game.execute(action)
    assert "Outcome: solved" in result
    assert game.limit_reached.is_set()
    saved = json.loads((tmp_path / "game.json").read_text(encoding="utf-8"))
    assert len(saved["actions"]) == 24 and saved["box"] == [3, 1]


def test_solving_before_limit_leaves_time_to_report(tmp_path: Path) -> None:
    game = SokobanAuthority(tmp_path)
    for action in ("left", "down", "down", "right", "up", "up"):
        result = game.execute(action)
    assert "Outcome: solved" in result and "Remaining: 18" in result
    assert not game.limit_reached.is_set()
    assert "Game already ended: solved" in game.execute("undo")
    assert game.summary() == {"outcome": "solved", "actions": 6, "limit": 24}


def test_failed_authoritative_save_does_not_advance_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    game = SokobanAuthority(tmp_path)
    before = (tmp_path / "game.json").read_bytes()
    files_before = set(tmp_path.iterdir())
    monkeypatch.setattr("sokoban_authority.os.replace", lambda *_: (_ for _ in ()).throw(OSError("disk error")))
    with pytest.raises(OSError):
        game.execute("up")
    assert game.failed.is_set()
    assert (tmp_path / "game.json").read_bytes() == before
    assert "Actions: 0 / 24" in game.execute("show")
    assert set(tmp_path.iterdir()) == files_before


def test_recorded_rules_replay_the_game_after_source_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    original = GAME_PATH.read_bytes()
    source.write_bytes(original)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    game = SokobanAuthority(run_dir, source)
    game.execute("down")
    snapshot = run_dir / "sokoban_rules.py"
    assert snapshot.read_bytes() == original
    assert Path(game.rules.__file__) == snapshot
    source.write_text("raise RuntimeError('rules were changed')", encoding="utf-8")
    game.execute("undo")
    replay = subprocess.run(
        [sys.executable, str(snapshot), "--state", str(game.path), "show"],
        capture_output=True, text=True, check=True,
    )
    assert replay.stdout.rstrip() == game.execute("show")
    assert snapshot.read_bytes() == original


def test_existing_rules_snapshot_cannot_be_overwritten(tmp_path: Path) -> None:
    snapshot = tmp_path / "sokoban_rules.py"
    snapshot.write_bytes(b"existing rules")
    with pytest.raises(FileExistsError):
        SokobanAuthority(tmp_path)
    assert snapshot.read_bytes() == b"existing rules"
