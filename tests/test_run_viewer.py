import json
import shutil
import subprocess
from pathlib import Path

import pytest

VIEWER = Path(__file__).resolve().parents[1] / "src" / "run_viewer" / "replay.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required to check the viewer's replay logic")


def run_viewer(script: str, data: dict) -> dict:
    result = subprocess.run(
        [NODE, "-e", script, str(VIEWER)],
        input=json.dumps(data), capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_replay_handles_blocked_moves_and_undo() -> None:
    result = run_viewer(
        "const r=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);"
        "process.stdin.on('end',()=>{const x=JSON.parse(s);console.log(JSON.stringify(r.replay(x.board,x.game)));});",
        {"board": ["#####", "# . #", "# $ #", "# @ #", "#####"],
         "game": {"player": [2, 3], "box": [2, 2], "action_limit": 4,
                  "actions": [{"action": "left", "result": "Moved."},
                              {"action": "left", "result": "Blocked; the board did not change."},
                              {"action": "undo", "result": "Move undone."}]}},
    )
    assert len(result["frames"]) == 4
    assert [frame["player"] for frame in result["frames"]] == [[2, 3], [1, 3], [1, 3], [2, 3]]
    assert result["frames"][2]["kind"] == "blocked"
    assert result["frames"][3]["kind"] == "undo"
    assert result["warnings"] == []


def test_legacy_board_extraction_and_inconsistent_record() -> None:
    result = run_viewer(
        "const r=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);"
        "process.stdin.on('end',()=>{const x=JSON.parse(s);"
        "console.log(JSON.stringify(r.replay(r.boardFromRules(x.rules),x.game)));});",
        {"rules": 'import os\nBOARD = (\n    "#####",\n    "# . #",\n    "# $ #",\n    "# @ #",\n    "#####",\n)\nos.system("not executed")',
         "game": {"player": [1, 1], "box": [2, 2], "actions": []}},
    )
    assert result["frames"][0]["player"] == [2, 3]
    assert any("final" in warning.lower() for warning in result["warnings"])


def test_undo_without_history_is_not_a_blocked_move() -> None:
    result = run_viewer(
        "const r=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);"
        "process.stdin.on('end',()=>{const x=JSON.parse(s);console.log(JSON.stringify(r.replay(x.board,x.game)));});",
        {"board": ["#####", "# . #", "# $ #", "# @ #", "#####"],
         "game": {"player": [2, 3], "box": [2, 2],
                  "actions": [{"action": "undo", "result": "Nothing to undo."}]}},
    )
    assert result["frames"][1]["kind"] == "empty"
    assert result["warnings"] == []


@pytest.mark.parametrize("reason", ["solved", "action_limit"])
def test_replay_rejects_actions_after_game_ends(reason: str) -> None:
    actions = ([{"action": "up", "result": "Moved."}, {"action": "undo", "result": "Move undone."}]
               if reason == "solved" else
               [{"action": "left", "result": "Moved."}, {"action": "right", "result": "Moved."}])
    result = run_viewer(
        "const r=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);"
        "process.stdin.on('end',()=>{const x=JSON.parse(s);try{r.replay(x.board,x.game);console.log(JSON.stringify({error:null}));}"
        "catch(e){console.log(JSON.stringify({error:e.message}));}});",
        {"board": ["#####", "# . #", "# $ #", "# @ #", "#####"],
         "game": {"player": [2, 3], "box": [2, 2], "action_limit": 8 if reason == "solved" else 1, "actions": actions}},
    )
    assert "ended" in (result["error"] or "").lower()


def test_replay_allows_solution_on_final_allowed_action() -> None:
    result = run_viewer(
        "const r=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);"
        "process.stdin.on('end',()=>{const x=JSON.parse(s);console.log(JSON.stringify(r.replay(x.board,x.game)));});",
        {"board": ["#####", "# . #", "# $ #", "# @ #", "#####"],
         "game": {"player": [2, 2], "box": [2, 1], "action_limit": 1,
                  "actions": [{"action": "up", "result": "Moved."}]}},
    )
    assert len(result["frames"]) == 2
    assert result["warnings"] == []
