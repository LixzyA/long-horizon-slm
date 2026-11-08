import argparse
import json
import os
import tempfile
from pathlib import Path

BOARD = (
    "#######",
    "#  .  #",
    "#  @  #",
    "#  $  #",
    "#     #",
    "#     #",
    "#######",
)
PUZZLE_PATH = Path(__file__).with_name("puzzle.json")
PUZZLE = json.loads(PUZZLE_PATH.read_text(encoding="utf-8")) if PUZZLE_PATH.exists() else None
if PUZZLE is not None:
    BOARD = tuple(PUZZLE["board"])
DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
WALLS = {(x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == "#"}
GOAL = next((x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == ".")
PLAYER = next((x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == "@")
BOX = next((x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == "$")
ACTION_LIMIT = PUZZLE["action_limit"] if PUZZLE is not None else 24


def initial_state() -> dict:
    return {
        "player": list(PLAYER), "box": list(BOX), "history": [], "actions": [],
        "action_limit": ACTION_LIMIT,
    }


def outcome(state: dict) -> str:
    if tuple(state["box"]) == GOAL:
        return "solved"
    if len(state["actions"]) >= state["action_limit"]:
        return "action_limit_reached"
    return "in_progress"


def play(state: dict, action: str) -> str:
    if outcome(state) != "in_progress":
        return f"Game already ended: {outcome(state)}."
    if action == "undo":
        if not state["history"]:
            message = "Nothing to undo."
        else:
            previous = state["history"].pop()
            state["player"], state["box"] = previous["player"], previous["box"]
            message = "Move undone."
    else:
        dx, dy = DIRECTIONS[action]
        px, py = state["player"]
        next_player = (px + dx, py + dy)
        box = tuple(state["box"])
        next_box = (box[0] + dx, box[1] + dy)
        if next_player in WALLS or (next_player == box and next_box in WALLS):
            message = "Blocked; the board did not change."
        else:
            state["history"].append({"player": state["player"][:], "box": state["box"][:]})
            state["player"] = list(next_player)
            if next_player == box:
                state["box"] = list(next_box)
            message = "Moved."
    state["actions"].append({"action": action, "result": message})
    return message


def validate_state(state: object) -> dict:
    if not isinstance(state, dict):
        raise TypeError("invalid state")
    limit = state.get("action_limit")
    actions = state.get("actions")
    if type(limit) is not int or limit <= 0 or not isinstance(actions, list) or len(actions) > limit:
        raise ValueError("invalid state limit or actions")
    if PUZZLE is not None and limit != ACTION_LIMIT:
        raise ValueError("state limit does not match the saved puzzle")
    expected = initial_state()
    expected["action_limit"] = limit
    for entry in actions:
        if not isinstance(entry, dict) or entry.get("action") not in (*DIRECTIONS, "undo"):
            raise ValueError("invalid state action")
        if outcome(expected) != "in_progress":
            raise ValueError("state has actions after the game ended")
        action = entry["action"]
        if entry != {"action": action, "result": play(expected, action)}:
            raise ValueError("invalid state action result")
    if json.dumps(state, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("state does not match its action history")
    return state


def display(state: dict) -> str:
    rows = [["#" if (x, y) in WALLS else "-" for x in range(len(BOARD[0]))] for y in range(len(BOARD))]
    gx, gy = GOAL
    rows[gy][gx] = "."
    bx, by = state["box"]
    rows[by][bx] = "*" if (bx, by) == GOAL else "$"
    px, py = state["player"]
    rows[py][px] = "+" if (px, py) == GOAL else "@"
    grid = ["    " + " ".join(str(x) for x in range(len(BOARD[0])))]
    grid.extend(f"{y}   {' '.join(row)}" for y, row in enumerate(rows))
    used = len(state["actions"])
    return "\n".join(grid) + (
        f"\n\nPlayer: row {py}, column {px}\nBox: row {by}, column {bx}"
        f"\nGoal: row {gy}, column {gx}\nActions: {used} / {state['action_limit']}"
        f"\nRemaining: {state['action_limit'] - used}\nOutcome: {outcome(state)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Play the one-box Sokoban pilot.")
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("action", choices=("init", "show", "up", "down", "left", "right", "undo"))
    args = parser.parse_args()
    try:
        if args.action == "init":
            state = initial_state()
            with args.state.open("x", encoding="utf-8") as file:
                json.dump(state, file, indent=2)
        else:
            state = validate_state(json.loads(args.state.read_text(encoding="utf-8")))
            if args.action != "show":
                before = outcome(state)
                message = play(state, args.action)
                if before == "in_progress":
                    temporary = None
                    try:
                        with tempfile.NamedTemporaryFile(
                            mode="w", encoding="utf-8", dir=args.state.parent, delete=False
                        ) as file:
                            temporary = Path(file.name)
                            json.dump(state, file, indent=2)
                        os.replace(temporary, args.state)
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                print(message)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Invalid or inaccessible game state: {exc}\n")
    print(display(state))


if __name__ == "__main__":
    main()
