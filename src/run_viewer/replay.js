/* Replay only the one-box Sokoban rules saved with these experiments. */
(function (root) {
  "use strict";

  const directions = {up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0]};
  const same = (a, b) => a[0] === b[0] && a[1] === b[1];
  const point = p => Array.isArray(p) && p.length === 2 && p.every(Number.isInteger);

  function boardFromRules(source) {
    const match = source.match(/^BOARD\s*=\s*\(([\s\S]*?)^\)/m);
    if (!match) throw new Error("Could not find a literal BOARD in the rules file. Select puzzle.json instead.");
    const rows = match[1].trim().split(/\r?\n/).map(line => {
      const row = line.match(/^\s*(["'])([# .@$+*\-]+)\1\s*,?\s*$/);
      if (!row) throw new Error("The saved board is not a simple Sokoban grid. Select puzzle.json instead.");
      return row[2];
    });
    return rows;
  }

  function replay(board, game) {
    if (!Array.isArray(board) || !board.length || !board.every(row => typeof row === "string" && row.length === board[0].length && /^[# .@$+*\-]+$/.test(row))) {
      throw new Error("The board must be a rectangular grid of Sokoban characters.");
    }
    if (!game || !Array.isArray(game.actions) || !point(game.player) || !point(game.box)) {
      throw new Error("game.json must contain player, box, and actions.");
    }
    let player, box, goal;
    const positions = {player: [], box: [], goal: []};
    board.forEach((row, y) => [...row].forEach((cell, x) => {
      if ("@+".includes(cell)) positions.player.push([x, y]);
      if ("$*".includes(cell)) positions.box.push([x, y]);
      if (".+*".includes(cell)) positions.goal.push([x, y]);
    }));
    if (Object.values(positions).some(items => items.length !== 1)) throw new Error("The board must have one player, one box, and one goal.");
    [player, box, goal] = [positions.player[0], positions.box[0], positions.goal[0]];
    const wall = ([x, y]) => y < 0 || y >= board.length || x < 0 || x >= board[0].length || board[y][x] === "#";
    const history = [];
    const warnings = [];
    const frames = [{player: [...player], box: [...box], kind: "start", action: null, result: "Starting position"}];
    game.actions.forEach((entry, index) => {
      if (same(box, goal) || (Number.isInteger(game.action_limit) && index >= game.action_limit)) {
        throw new Error(`Action ${index + 1} was recorded after the game ended.`);
      }
      if (!entry || (entry.action !== "undo" && !Object.hasOwn(directions, entry.action))) throw new Error(`Unknown action at step ${index + 1}.`);
      let kind, result;
      if (entry.action === "undo") {
        if (!history.length) { kind = "empty"; result = "Nothing to undo."; }
        else { ({player, box} = history.pop()); kind = "undo"; result = "Move undone."; }
      } else {
        const [dx, dy] = directions[entry.action];
        const next = [player[0] + dx, player[1] + dy];
        const nextBox = [box[0] + dx, box[1] + dy];
        if (wall(next) || (same(next, box) && wall(nextBox))) { kind = "blocked"; result = "Blocked; the board did not change."; }
        else {
          history.push({player: [...player], box: [...box]});
          kind = same(next, box) ? "push" : "move";
          if (kind === "push") box = nextBox;
          player = next;
          result = "Moved.";
        }
      }
      if (entry.result !== result) warnings.push(`Action ${index + 1}: saved result differs from the reconstructed move.`);
      frames.push({player: [...player], box: [...box], action: entry.action, kind, result: entry.result || result});
    });
    if (!same(player, game.player) || !same(box, game.box)) warnings.push("The reconstructed final position differs from game.json. The replay may not represent this saved state.");
    if (Array.isArray(game.history) && JSON.stringify(history) !== JSON.stringify(game.history)) warnings.push("The reconstructed undo history differs from game.json.");
    return {board, goal, frames, warnings};
  }

  const api = {replay, boardFromRules};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SokobanReplay = api;
})(globalThis);
