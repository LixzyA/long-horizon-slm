import argparse
import json
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
DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
WALLS = {(x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == "#"}
GOAL = next((x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == ".")
PLAYER = next((x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == "@")
BOX = next((x, y) for y, row in enumerate(BOARD) for x, cell in enumerate(row) if cell == "$")


def initial_state() -> dict:
    return {"player": list(PLAYER), "box": list(BOX), "history": [], "actions": []}


def play(state: dict, action: str) -> str:
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


def display(state: dict) -> str:
    rows = [["#" if (x, y) in WALLS else " " for x in range(len(BOARD[0]))] for y in range(len(BOARD))]
    gx, gy = GOAL
    rows[gy][gx] = "."
    bx, by = state["box"]
    rows[by][bx] = "*" if (bx, by) == GOAL else "$"
    px, py = state["player"]
    rows[py][px] = "+" if (px, py) == GOAL else "@"
    solved = tuple(state["box"]) == GOAL
    return "\n".join("".join(row) for row in rows) + ("\nSolved!" if solved else "\nNot solved.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play the one-box Sokoban pilot.")
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("action", choices=("init", "show", "up", "down", "left", "right", "undo"))
    args = parser.parse_args()
    if args.action == "init":
        state = initial_state()
        with args.state.open("x", encoding="utf-8") as file:
            json.dump(state, file, indent=2)
    else:
        state = json.loads(args.state.read_text(encoding="utf-8"))
        if args.action != "show":
            print(play(state, args.action))
            args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(display(state))


if __name__ == "__main__":
    main()
