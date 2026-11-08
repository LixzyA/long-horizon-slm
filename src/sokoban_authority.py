import copy
import importlib.util
import json
import os
import tempfile
import threading
from pathlib import Path

GAME_PATH = Path(__file__).resolve().parent.parent / "sokoban_workspace" / "src" / "sokoban.py"
PUZZLES_PATH = Path(__file__).resolve().parent / "sokoban" / "puzzles.json"


def load_puzzle(puzzle_id: str) -> dict:
    puzzles = json.loads(PUZZLES_PATH.read_text(encoding="utf-8"))
    return {"id": puzzle_id, **puzzles[puzzle_id]}


class SokobanAuthority:
    """Own one game outside the agent's writable workspace."""

    def __init__(self, run_dir: Path, rules_path: Path = GAME_PATH, puzzle_id: str | None = None) -> None:
        rules = rules_path.read_bytes()
        snapshot = Path(run_dir) / "sokoban_rules.py"
        with snapshot.open("xb") as file:
            file.write(rules)
        if puzzle_id is not None:
            puzzle = load_puzzle(puzzle_id)
            with (Path(run_dir) / "puzzle.json").open("x", encoding="utf-8") as file:
                json.dump(puzzle, file, indent=2)
        spec = importlib.util.spec_from_file_location("sokoban_rules", snapshot)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load Sokoban rules")
        self.rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rules)
        self.path = Path(run_dir) / "game.json"
        self.lock = threading.Lock()
        self.closed = False
        self.limit_reached = threading.Event()
        self.failed = threading.Event()
        self.state = self.rules.initial_state()
        with self.path.open("x", encoding="utf-8") as file:
            json.dump(self.state, file, indent=2)

    def close(self) -> None:
        """Wait for the current action and prevent further game changes."""
        with self.lock:
            self.closed = True

    def summary(self) -> dict:
        with self.lock:
            return {
                "outcome": self.rules.outcome(self.state),
                "actions": len(self.state["actions"]),
                "limit": self.state["action_limit"],
            }

    def execute(self, action: str) -> str:
        if action not in (*self.rules.DIRECTIONS, "undo", "show", "history"):
            raise ValueError("Unknown game action")
        with self.lock:
            if action == "show":
                return self.rules.display(self.state)
            if action == "history":
                history = copy.deepcopy(self.state)
                history["coordinate_order"] = ["column", "row"]
                history["actions_used"] = len(self.state["actions"])
                history["remaining"] = self.state["action_limit"] - history["actions_used"]
                return json.dumps(history, indent=2)
            if self.closed:
                return "Game session has ended.\n" + self.rules.display(self.state)
            state = copy.deepcopy(self.state)
            before = self.rules.outcome(state)
            message = self.rules.play(state, action)
            if before == "in_progress":
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                    ) as file:
                        temporary = Path(file.name)
                        json.dump(state, file, indent=2)
                    os.replace(temporary, self.path)
                except OSError:
                    self.failed.set()
                    raise
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                self.state = state
                if len(state["actions"]) == state["action_limit"]:
                    self.limit_reached.set()
            return message + "\n" + self.rules.display(self.state)
