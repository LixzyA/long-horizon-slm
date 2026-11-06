import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import container_run
import network_guard
import supervisor
from sokoban_authority import SokobanAuthority


@pytest.mark.skipif(os.environ.get("RUN_SOKOBAN_DOCKER_TEST") != "1", reason="requires Docker and Ollama")
def test_container_game_stops_agent_on_action_24(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    workspace = container_run.prepare_workspace(
        ROOT / "sokoban_workspace", run_dir, require_agents=False
    )
    (workspace / "output").mkdir()
    game = SokobanAuthority(run_dir, workspace / "src" / "sokoban.py")
    (workspace / "src" / "sokoban.py").unlink()
    (workspace / "fake_agent.py").write_text(
        '''import json, subprocess, sys
from pathlib import Path
for line in sys.stdin:
    request = json.loads(line)
    if request["type"] == "get_state":
        print(json.dumps({"type": "response", "id": request["id"], "success": True}), flush=True)
    elif request["type"] == "prompt":
        print(json.dumps({"type": "response", "id": request["id"], "success": True}), flush=True)
        for i in range(24):
            result = subprocess.run([sys.executable, "src/play.py", "undo"], capture_output=True, text=True)
            if i < 23 and (result.returncode or f"Remaining: {23-i}" not in result.stdout):
                raise SystemExit(2)
            if i == 2:
                fake_state = Path("output/game.json")
                fake_state.write_text("{}")
                fake_state.unlink()
                restart = subprocess.run([sys.executable, "src/play.py", "init"], capture_output=True)
                current = subprocess.run([sys.executable, "src/play.py", "show"], capture_output=True, text=True)
                history = subprocess.run([sys.executable, "src/play.py", "history"], capture_output=True, text=True)
                if restart.returncode == 0 or "Actions: 3 / 24" not in current.stdout or json.loads(history.stdout)["remaining"] != 21:
                    raise SystemExit(3)
        print(json.dumps({"type": "agent_settled"}), flush=True)
''', encoding="utf-8",
    )
    token = secrets.token_urlsafe(32)
    name = "long-horizon-test-" + uuid.uuid4().hex
    guard = network_guard.GatewaySession(name, token, "unused", game=game)
    try:
        guard.start()
        command = container_run.container_command(workspace, name, guard.network, token)
        command = command[:-1] + ["--entrypoint", "python", command[-1], "-u", "fake_agent.py"]
        result = supervisor.supervise(
            command, "test", 60, run_dir, game=game,
            stop_at_limit=lambda: container_run.cleanup_container(name),
        )
        assert result["status"] == "action_limit"
        assert result["termination"] == "forced"
        assert result["game"] == {"outcome": "action_limit_reached", "actions": 24, "limit": 24}
        assert len(json.loads(game.path.read_text(encoding="utf-8"))["actions"]) == 24
        assert not (workspace / "output" / "game.json").exists()
    finally:
        container_run.cleanup_container(name)
        assert guard.close()
