"use strict";

const $ = id => document.getElementById(id);
const arrows = {up: "↑", down: "↓", left: "←", right: "→", undo: "↶"};
const kindLabel = {start: "START", move: "MOVED", blocked: "BLOCKED", push: "PUSHED", undo: "UNDONE", empty: "NO UNDO"};
let view, step = 0, timer = null, chosenFiles = [], request = 0;

const demoBoard = ["#######", "#  .  #", "#  $  #", "# @   #", "#     #", "#######"];
const demoGame = {player: [3, 2], box: [3, 1], action_limit: 12, actions: [
  {action: "left", result: "Moved."},
  {action: "left", result: "Blocked; the board did not change."},
  {action: "undo", result: "Move undone."},
  {action: "right", result: "Moved."},
  {action: "up", result: "Moved."}
]};

function showNotice(message) {
  $("notice").hidden = !message;
  $("notice").textContent = message;
}
function stop() {
  clearInterval(timer);
  timer = null;
  $("play").textContent = "▶";
  $("play").setAttribute("aria-label", "Play replay");
}
function pathOf(file) { return file.webkitRelativePath || file.name; }
function runId(file) { return pathOf(file).match(/(?:^|\/)(\d{8}-\d{6}-[a-f0-9]{8})(?:\/|$)/i)?.[1]; }
function relatedFile(gameFile, names) {
  const gamePath = pathOf(gameFile).split("/");
  const id = runId(gameFile);
  return chosenFiles.filter(file => names.includes(file.name) && (!id || !runId(file) || runId(file) === id))
    .map(file => {
      const parts = pathOf(file).split("/");
      let common = 0;
      while (common < Math.min(parts.length - 1, gamePath.length - 1) && parts[common] === gamePath[common]) common++;
      return {file, common, priority: names.indexOf(file.name)};
    }).sort((a, b) => b.common - a.common || a.priority - b.priority)[0]?.file;
}
async function textOf(file) {
  if (file.size > 4 * 1024 * 1024) throw new Error(`${file.name} is larger than 4 MB.`);
  return file.text();
}
async function openGame(gameFile) {
  const thisRequest = ++request;
  stop();
  try {
    const game = JSON.parse(await textOf(gameFile));
    const puzzleFile = relatedFile(gameFile, ["puzzle.json"]);
    const rulesFile = relatedFile(gameFile, ["sokoban_rules.py", "sokoban.py"]);
    let board;
    if (puzzleFile) board = JSON.parse(await textOf(puzzleFile)).board;
    else if (rulesFile) {
      const rules = await textOf(rulesFile);
      if (/BOARD\s*=\s*tuple\(PUZZLE\s*\[/.test(rules)) throw new Error("This rules file uses puzzle.json. Select it with game.json.");
      board = SokobanReplay.boardFromRules(rules);
    } else throw new Error("Select game.json together with its puzzle.json, sokoban_rules.py, or workspace/src/sokoban.py. You can also open the whole run folder.");
    const replay = SokobanReplay.replay(board, game);
    if (thisRequest !== request) return;
    view = {game, replay};
    $("run-name").textContent = runId(gameFile) || pathOf(gameFile);
    $("source-tag").textContent = puzzleFile ? "PUZZLE + GAME" : "RULES + GAME";
    showNotice(replay.warnings.join(" "));
    renderRun();
  } catch (error) {
    if (thisRequest === request) showNotice(`Could not open this run: ${error.message}`);
  }
}
function loadFiles(files) {
  chosenFiles = Array.from(files);
  const games = chosenFiles.filter(file => file.name === "game.json");
  if (!games.length) { showNotice("No game.json found. Choose a Sokoban run folder or select game.json and its board file."); return; }
  const select = $("game-select");
  select.replaceChildren();
  games.forEach((file, i) => {
    const option = document.createElement("option");
    option.value = String(i);
    option.textContent = pathOf(file);
    select.append(option);
  });
  $("game-label").hidden = games.length < 2;
  select.onchange = () => openGame(games[Number(select.value)]);
  openGame(games[0]);
}
function loadDemo() {
  request++;
  chosenFiles = [];
  stop();
  view = {game: demoGame, replay: SokobanReplay.replay(demoBoard, demoGame)};
  $("run-name").textContent = "Example replay";
  $("source-tag").textContent = "DEMO";
  $("game-label").hidden = true;
  showNotice("");
  renderRun();
}
function same(a, b) { return a[0] === b[0] && a[1] === b[1]; }
function renderRun() {
  const {game, replay} = view;
  const actions = replay.frames.slice(1);
  const solved = same(game.box, replay.goal);
  const limited = Number.isInteger(game.action_limit) && actions.length >= game.action_limit;
  $("metric-outcome").textContent = replay.warnings.length ? "Check record" : solved ? "Solved" : limited ? "Action limit" : "In progress";
  $("metric-status").textContent = replay.warnings.length ? "Replay has inconsistencies" : "Final saved game";
  $("metric-actions").textContent = `${actions.length} / ${Number.isInteger(game.action_limit) ? game.action_limit : "—"}`;
  $("metric-blocked").textContent = actions.filter(a => a.kind === "blocked").length;
  $("metric-pushes").textContent = actions.filter(a => a.kind === "push").length;
  $("metric-undo").textContent = actions.filter(a => a.action === "undo").length;
  $("timeline-count").textContent = `${actions.length} ACTION${actions.length === 1 ? "" : "S"}`;
  $("scrubber").max = String(actions.length);
  const timeline = $("timeline");
  timeline.replaceChildren();
  replay.frames.forEach((frame, index) => {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.step = String(index);
    button.setAttribute("aria-label", index ? `Step ${index}, ${frame.action}, ${frame.kind}` : "Step 0, starting position");
    const left = document.createElement("span"); left.className = "timeline-left";
    const number = document.createElement("span"); number.className = "timeline-number"; number.textContent = String(index).padStart(2, "0");
    const icon = document.createElement("span"); icon.className = "action-arrow"; icon.textContent = arrows[frame.action] || "·"; icon.setAttribute("aria-hidden", "true");
    const detail = document.createElement("span");
    const name = document.createElement("span"); name.className = "action-name"; name.textContent = frame.action || "Start";
    const position = document.createElement("span"); position.className = "action-position"; position.textContent = `PLAYER ${frame.player[1]}, ${frame.player[0]}`;
    detail.append(name, position); left.append(number, icon, detail);
    const result = document.createElement("span"); result.className = `result ${frame.kind}`; result.textContent = kindLabel[frame.kind];
    button.append(left, result); button.addEventListener("click", () => { stop(); go(index); }); li.append(button); timeline.append(li);
  });
  go(0);
}
function go(nextStep) {
  step = Math.max(0, Math.min(nextStep, view.replay.frames.length - 1));
  const {board, goal, frames} = view.replay;
  const frame = frames[step];
  const element = $("board"); element.replaceChildren();
  element.style.gridTemplateColumns = `repeat(${board[0].length + 1}, var(--cell))`;
  const coordinate = value => { const node = document.createElement("div"); node.className = "coordinate"; node.textContent = value; return node; };
  element.append(coordinate(""));
  for (let x = 0; x < board[0].length; x++) element.append(coordinate(x));
  board.forEach((row, y) => {
    element.append(coordinate(y));
    [...row].forEach((char, x) => {
      const cell = document.createElement("div"); cell.className = `cell${char === "#" ? " wall" : ""}`;
      const location = [x, y];
      const token = document.createElement("span");
      if (same(location, frame.player)) { token.className = `player${same(location, goal) ? " on-goal" : ""}`; token.textContent = "P"; }
      else if (same(location, frame.box)) { token.className = `box${same(location, goal) ? " on-goal" : ""}`; token.textContent = "B"; }
      else if (same(location, goal)) token.className = "goal";
      if (token.className) cell.append(token);
      element.append(cell);
    });
  });
  element.setAttribute("aria-label", `Board at step ${step}. Player row ${frame.player[1]}, column ${frame.player[0]}. Box row ${frame.box[1]}, column ${frame.box[0]}. Goal row ${goal[1]}, column ${goal[0]}.`);
  $("frame-badge").className = `badge ${frame.kind}`;
  $("frame-badge").textContent = step ? `${frame.action.toUpperCase()} · ${kindLabel[frame.kind]}` : "START";
  $("step-label").replaceChildren(document.createTextNode(`STEP ${step} `));
  const total = document.createElement("span"); total.textContent = `/ ${frames.length - 1}`; $("step-label").append(total);
  $("scrubber").value = String(step);
  $("first").disabled = $("previous").disabled = step === 0;
  $("last").disabled = $("next").disabled = step === frames.length - 1;
  $("play").disabled = frames.length === 1;
  const buttons = $("timeline").querySelectorAll("button");
  buttons.forEach((button, i) => { button.classList.toggle("active", i === step); if (i === step) button.setAttribute("aria-current", "step"); else button.removeAttribute("aria-current"); });
  const active = buttons[step];
  if (active) {
    const list = $("timeline");
    const itemRect = active.getBoundingClientRect(), listRect = list.getBoundingClientRect();
    if (itemRect.top < listRect.top) list.scrollTop -= listRect.top - itemRect.top;
    else if (itemRect.bottom > listRect.bottom) list.scrollTop += itemRect.bottom - listRect.bottom;
  }
}
$("file-input").addEventListener("change", event => { loadFiles(event.target.files); event.target.value = ""; });
$("folder-input").addEventListener("change", event => { loadFiles(event.target.files); event.target.value = ""; });
$("demo-button").addEventListener("click", loadDemo);
$("first").addEventListener("click", () => { stop(); go(0); });
$("previous").addEventListener("click", () => { stop(); go(step - 1); });
$("next").addEventListener("click", () => { stop(); go(step + 1); });
$("last").addEventListener("click", () => { stop(); go(view.replay.frames.length - 1); });
$("scrubber").addEventListener("input", event => { stop(); go(Number(event.target.value)); });
$("play").addEventListener("click", () => {
  if (timer) { stop(); return; }
  if (step === view.replay.frames.length - 1) go(0);
  $("play").textContent = "❚❚";
  $("play").setAttribute("aria-label", "Pause replay");
  timer = setInterval(() => { go(step + 1); if (step === view.replay.frames.length - 1) stop(); }, Number($("speed").value));
});
$("speed").addEventListener("change", stop);
document.addEventListener("keydown", event => {
  if (["INPUT", "SELECT", "BUTTON"].includes(event.target.tagName)) return;
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); stop(); go(step + (event.key === "ArrowRight" ? 1 : -1)); }
});
loadDemo();
