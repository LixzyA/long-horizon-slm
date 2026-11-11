import json
import sys
from collections import Counter, deque
from itertools import combinations
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import supervisor
import sokoban_authority
from sokoban_authority import PUZZLES_DIR, SokobanAuthority, load_puzzles


def floor_transforms(board: list[str]):
    floor = {(x, y) for y, row in enumerate(board) for x, cell in enumerate(row) if cell != "#"}
    for _ in range(4):
        yield floor
        yield {(-x, y) for x, y in floor}
        floor = {(-y, x) for x, y in floor}


def floor_distance(first: list[str], second: list[str]) -> int:
    left = next(floor_transforms(first))
    right = next(floor_transforms(second))
    if abs(len(left) - len(right)) >= 5:
        return 5
    distance = len(left) + len(right)
    for transformed in floor_transforms(second):
        overlaps = Counter((ax - bx, ay - by) for ax, ay in left for bx, by in transformed)
        distance = min(distance, len(left) + len(right) - 2 * max(overlaps.values()))
    return distance


def shortest_path_and_recovery(rules):
    initial = (rules.PLAYER, rules.BOX)
    parents = {initial: None}
    queue = deque([initial])
    goal = None
    while queue:
        player, box = queue.popleft()
        if box == rules.GOAL:
            goal = (player, box)
            break
        for action, (dx, dy) in rules.DIRECTIONS.items():
            nxt = (player[0] + dx, player[1] + dy)
            if nxt in rules.WALLS:
                continue
            new_box = box
            if nxt == box:
                new_box = (box[0] + dx, box[1] + dy)
                if new_box in rules.WALLS:
                    continue
            state = (nxt, new_box)
            if state not in parents:
                parents[state] = ((player, box), action)
                queue.append(state)
    assert goal is not None
    steps = []
    while parents[goal] is not None:
        previous, action = parents[goal]
        steps.append((previous, action))
        goal = previous
    steps.reverse()
    recovery = None
    for index, ((player, box), _) in enumerate(steps):
        for action, (dx, dy) in rules.DIRECTIONS.items():
            if (player[0] + dx, player[1] + dy) != box:
                continue
            target = (box[0] + dx, box[1] + dy)
            x, y = target
            if target not in rules.WALLS and target != rules.GOAL and (
                ((x - 1, y) in rules.WALLS or (x + 1, y) in rules.WALLS)
                and ((x, y - 1) in rules.WALLS or (x, y + 1) in rules.WALLS)
            ):
                recovery = (index, action)
                break
        if recovery is not None:
            break
    return [action for _, action in steps], recovery


def test_board_splits_are_disjoint_and_distinct() -> None:
    puzzles = load_puzzles()
    assert len(puzzles) == 70
    assert Counter(p["split"] for p in puzzles.values()) == {"train": 30, "validation": 20, "test": 20}
    seen = set()
    for split, count in (("train", 30), ("validation", 20), ("test", 20)):
        records = json.loads((PUZZLES_DIR / f"puzzles-{split}.json").read_text(encoding="utf-8"))
        assert len(records) == count
        assert all(item["split"] == split for item in records.values())
        assert not seen.intersection(records)
        seen.update(records)
    assert seen == set(puzzles)
    assert all(puzzles[name]["split"] == "train" for name in ("one-push", "align", "baseline", "offset", "detour"))
    for name, puzzle in puzzles.items():
        board = puzzle["board"]
        assert len(board) >= 3 and len({len(row) for row in board}) == 1, name
        assert set("".join(board)) <= set("# @$."), name
        assert set(board[0] + board[-1]) == {"#"}, name
        assert all(row[0] == row[-1] == "#" for row in board), name
        assert all(sum(row.count(c) for row in board) == 1 for c in "@$."), name
        floor = next(floor_transforms(board))
        reached = {next(iter(floor))}
        queue = deque(reached)
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                point = (x + dx, y + dy)
                if point in floor and point not in reached:
                    reached.add(point)
                    queue.append(point)
        assert reached == floor, name
    for (name_a, a), (name_b, b) in combinations(puzzles.items(), 2):
        if a["split"] != b["split"]:
            assert floor_distance(a["board"], b["board"]) >= 5, (name_a, name_b)


def test_all_boards_solve_and_new_boards_allow_recovery(tmp_path: Path) -> None:
    puzzles = load_puzzles()
    legacy = {"one-push", "align", "baseline", "offset", "detour"}
    for name, puzzle in puzzles.items():
        run = tmp_path / name
        run.mkdir()
        game = SokobanAuthority(run, puzzle_id=name)
        rules = game.rules
        path, recovery = shortest_path_and_recovery(rules)
        assert len(path) == puzzle["shortest_actions"], name
        assert len(path) <= puzzle["action_limit"], name
        state = rules.initial_state()
        for action in path:
            assert rules.play(state, action) == "Moved.", name
        assert rules.outcome(state) == "solved", name
        if name not in legacy:
            assert 10 <= len(path) <= 32, name
            assert puzzle["action_limit"] == 2 * len(path) + 8, name
            assert recovery is not None, name
            index, wrong_action = recovery
            state = rules.initial_state()
            for action in path[:index]:
                assert rules.play(state, action) == "Moved.", name
            saved = (state["player"][:], state["box"][:])
            assert rules.play(state, wrong_action) == "Moved.", name
            assert rules.play(state, "undo") == "Move undone.", name
            assert (state["player"], state["box"]) == saved, name
            for action in path[index:]:
                assert rules.play(state, action) == "Moved.", name
            assert rules.outcome(state) == "solved", name
            assert len(state["actions"]) <= puzzle["action_limit"], name


@pytest.mark.parametrize("board_id,split", [("train-01", "train"), ("validation-01", "validation"), ("test-01", "test")])
def test_supervisor_selects_a_new_board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, board_id: str, split: str) -> None:
    import shutil

    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "sokoban_workspace", tmp_path / "sokoban_workspace")
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["supervisor.py", "--puzzle", board_id, "--llama-server", "x", "--model-file", "y"])

    class Backend:
        def __init__(self, *args):
            self.model = "model"
            self.token = "token"
            self.info = {}
        def start(self):
            return self.info
        def close(self):
            return True

    class Guard:
        def __init__(self, *args, **kwargs):
            self.network = "network"
        def start(self):
            pass
        def close(self):
            return True

    def run(command, prompt, limit, run_dir, *, game, **kwargs):
        puzzle = json.loads((run_dir / "puzzle.json").read_text(encoding="utf-8"))
        assert puzzle["id"] == board_id and puzzle["split"] == split
        assert game.state["action_limit"] == puzzle["action_limit"]
        assert f"You have {puzzle['action_limit']} actions" in prompt
        return {"status": "settled"}

    monkeypatch.setattr(supervisor.llamacpp_model, "LlamaServer", Backend)
    monkeypatch.setattr(supervisor.network_guard, "resolve_image", lambda _: "sha256:" + "a" * 64)
    monkeypatch.setattr(supervisor.network_guard, "GatewaySession", Guard)
    monkeypatch.setattr(supervisor.container_run, "cleanup_container", lambda _: True)
    monkeypatch.setattr(supervisor, "supervise", run)
    assert supervisor.main() == 0
    outcome = next((tmp_path / "supervisor-runs" / "local").glob("*/outcome.json"))
    assert json.loads(outcome.read_text(encoding="utf-8"))["game"]["outcome"] == "in_progress"


def test_duplicate_board_ids_across_split_files_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for split, records in {
        "train": {"same-id": {"split": "train"}},
        "validation": {"same-id": {"split": "validation"}},
        "test": {},
    }.items():
        (tmp_path / f"puzzles-{split}.json").write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setattr(sokoban_authority, "PUZZLES_DIR", tmp_path)
    with pytest.raises(ValueError, match="same-id"):
        load_puzzles()


def test_mislabeled_board_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "puzzles-train.json").write_text(json.dumps({"wrong": {"split": "test"}}), encoding="utf-8")
    monkeypatch.setattr(sokoban_authority, "PUZZLES_DIR", tmp_path)
    with pytest.raises(ValueError, match="wrong"):
        load_puzzles()
