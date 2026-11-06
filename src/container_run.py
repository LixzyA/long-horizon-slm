import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE = "long-horizon-pi:1.4.0"


def prepare_workspace(source: Path, run_dir: Path, *, require_agents: bool = True) -> Path:
    if source.is_symlink() or os.path.isjunction(source):
        raise ValueError(f"Workspace contains a link or junction: {source}")
    for root, directories, files in os.walk(source, followlinks=False):
        for name in directories + files:
            entry = Path(root) / name
            if entry.is_symlink() or os.path.isjunction(entry):
                raise ValueError(f"Workspace contains a link or junction: {entry}")
    workspace = run_dir / "workspace"
    shutil.copytree(source, workspace)
    agents = workspace / "AGENTS.md"
    if not require_agents and not agents.exists():
        return workspace
    text = agents.read_text(encoding="utf-8")
    _, separator, remainder = text.partition("# Run output")
    if not separator:
        raise ValueError("Workspace AGENTS.md is missing the run output section.")
    agents.write_text(
        "# Environment and tool use\n\n"
        "The working directory is /workspace in a Linux container. Use relative paths. "
        "Do not search outside /workspace or install software. If a command fails, "
        "inspect the error and do not repeat it unchanged.\n\n"
        "Use python3 for Python. If a required tool or source is unavailable, "
        "record the limitation and do not invent results.\n\n" + separator + remainder,
        encoding="utf-8",
    )
    return workspace


def container_command(
    workspace: Path, name: str, network: str, token: str, thinking_mode: str = "high"
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--network",
        network,
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=2g",
        "--tmpfs",
        "/tmp:rw,exec,nosuid,size=256m",
        "--mount",
        f"type=bind,src={workspace},dst=/workspace",
        "--env",
        f"MODEL_PROXY_TOKEN={token}",
        "--env",
        f"THINKING_MODE={thinking_mode}",
        "--env",
        "HTTP_PROXY=http://gateway:3128",
        "--env",
        "HTTPS_PROXY=http://gateway:3128",
        "--env",
        "http_proxy=http://gateway:3128",
        "--env",
        "https_proxy=http://gateway:3128",
        "--env",
        "NO_PROXY=gateway,localhost,127.0.0.1",
        "--env",
        "no_proxy=gateway,localhost,127.0.0.1",
        IMAGE,
    ]


def cleanup_container(name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0 or "No such container" in result.stderr:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"Could not remove container {name}; check Docker manually.", file=sys.stderr)
    return False


def new_token() -> str:
    return secrets.token_urlsafe(32)
