import argparse
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
import tomllib
import uuid
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import container_run
import llamacpp_model
import network_guard
from sokoban_authority import SokobanAuthority
from windows_job import bootstrap, checked, create_job, kernel32

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "experiment_workspace"
PROMPT = "Complete the assignment below. Use the current directory as your working directory.\n\n"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class LoopDetector:
    """Count consecutive failed tool calls in start order."""

    def __init__(self) -> None:
        self.pending: deque[dict[str, Any]] = deque()
        self.by_id: dict[str, dict[str, Any]] = {}
        self.last_signature: tuple[str, str] | None = None
        self.failures = 0
        self.detection: dict[str, Any] | None = None

    def observe(self, event: dict[str, Any]) -> bool:
        event_type = event.get("type")
        if event_type == "tool_execution_start":
            call_id = event.get("toolCallId")
            name = event.get("toolName")
            args = event.get("args")
            if (
                not isinstance(call_id, str)
                or not isinstance(name, str)
                or not isinstance(args, dict)
                or call_id in self.by_id
            ):
                self.pending.clear()
                self.by_id.clear()
                self.last_signature = None
                self.failures = 0
                return False
            call = {
                "id": call_id,
                "name": name,
                "signature": (
                    name,
                    json.dumps(args, sort_keys=True, ensure_ascii=False),
                ),
                "failed": None,
            }
            self.pending.append(call)
            self.by_id[call_id] = call
        elif event_type == "tool_execution_end":
            call = self.by_id.get(event.get("toolCallId"))
            if call is None or call["failed"] is not None:
                self.pending.clear()
                self.by_id.clear()
                self.last_signature = None
                self.failures = 0
                return False
            call["failed"] = event.get("isError") is True
            while self.pending and self.pending[0]["failed"] is not None:
                finished = self.pending.popleft()
                del self.by_id[finished["id"]]
                if not finished["failed"]:
                    self.last_signature = None
                    self.failures = 0
                elif finished["signature"] == self.last_signature:
                    self.failures += 1
                else:
                    self.last_signature = finished["signature"]
                    self.failures = 1
                if self.failures == 10:
                    self.detection = {
                        "tool_name": finished["name"],
                        "tool_call_id": finished["id"],
                        "failure_count": self.failures,
                    }
                    return True
            # Later completed calls can form a streak even if an earlier call is still running.
            signature = None
            failures = 0
            for finished in self.pending:
                if finished["failed"] is not True:
                    signature = None
                    failures = 0
                elif finished["signature"] == signature:
                    failures += 1
                else:
                    signature = finished["signature"]
                    failures = 1
                if failures == 10:
                    self.detection = {
                        "tool_name": finished["name"],
                        "tool_call_id": finished["id"],
                        "failure_count": failures,
                    }
                    return True
        return False



def supervise(
    command: list[str],
    prompt: str,
    limit_seconds: float,
    run_dir: Path,
    grace_seconds: float = 5,
    startup_seconds: float = 60,
    game: SokobanAuthority | None = None,
    stop_at_limit: Callable[[], bool] | None = None,
    backend: llamacpp_model.LlamaServer | None = None,
) -> dict[str, Any]:
    if not math.isfinite(limit_seconds) or limit_seconds <= 0:
        raise ValueError("Time limit must be a positive finite number.")
    if os.name != "nt":
        raise RuntimeError("This supervisor requires Windows Job Objects.")
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    events_path = run_dir / "events.jsonl"
    outcome_path = run_dir / "outcome.json"
    if events_path.exists() or outcome_path.exists():
        raise FileExistsError("Run directory already contains supervisor records.")
    dll = kernel32()
    job = create_job()
    process = None
    reader = None
    result = {
        "status": "startup_error",
        "termination": None,
        "limit_seconds": limit_seconds,
        "launched_at_utc": utc_now(),
        "prompt_submitted_at_utc": None,
        "ended_at_utc": None,
    }
    try:
        checked(dll.SetHandleInformation(job, 1, 1))
        args = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--job-bootstrap",
            str(job),
            *command,
        ]
        process = subprocess.Popen(
            args,
            cwd=WORKSPACE,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        checked(dll.SetHandleInformation(job, 1, 0))
        pending = queue.Queue()

        def read_output():
            try:
                for line in iter(process.stdout.readline, b""):
                    pending.put(line)
            finally:
                pending.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        with events_path.open("x", encoding="utf-8", buffering=1) as events:

            def send(message):
                process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
                process.stdin.flush()

            def receive(deadline, watch_game=False):
                while True:
                    if backend is not None:
                        backend.check_alive()
                    if watch_game and game is not None:
                        if game.limit_reached.is_set():
                            return {"type": "sokoban_action_limit"}
                        if game.failed.is_set():
                            raise RuntimeError("Sokoban game service failed.")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    try:
                        line = pending.get(timeout=min(remaining, 0.1) if watch_game or backend is not None else remaining)
                    except queue.Empty:
                        if watch_game or backend is not None:
                            continue
                        return None
                    if line is None:
                        raise RuntimeError("Agent exited before the operation settled.")
                    try:
                        record = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        print(
                            line.decode("utf-8", errors="replace"),
                            end="",
                            file=sys.stderr,
                            flush=True,
                        )
                        continue
                    if not isinstance(record, dict):
                        raise RuntimeError("Agent emitted a non-object JSON record.")
                    if record.get("type") not in (
                        "message_update",
                        "tool_execution_update",
                    ):
                        events.write(json.dumps(record, ensure_ascii=False) + "\n")
                    return record

            startup_deadline = time.monotonic() + startup_seconds
            send({"id": "supervisor-ready", "type": "get_state"})
            while True:
                event = receive(startup_deadline)
                if event is None:
                    raise RuntimeError(
                        "Pi did not become ready within the startup limit."
                    )
                if (
                    event.get("type") == "response"
                    and event.get("id") == "supervisor-ready"
                ):
                    if not event.get("success"):
                        raise RuntimeError("Pi rejected the readiness request.")
                    break
            send({"id": "supervisor-prompt", "type": "prompt", "message": prompt})
            result["prompt_submitted_at_utc"] = utc_now()
            start = time.monotonic()
            deadline = start + limit_seconds
            detector = LoopDetector()
            last_assistant = {}
            while True:
                event = receive(deadline, watch_game=game is not None)
                if event is None:
                    result["status"] = "timeout"
                    break
                if event.get("type") == "sokoban_action_limit" or (
                    game is not None and game.limit_reached.is_set()
                ):
                    result["status"] = "action_limit"
                    break
                if (
                    event.get("type") == "response"
                    and event.get("id") == "supervisor-prompt"
                    and not event.get("success")
                ):
                    raise RuntimeError("Pi rejected the prompt.")
                if detector.observe(event):
                    result["status"] = "loop_detected"
                    result["loop_detection"] = detector.detection
                    break
                if event.get("type") == "message_end":
                    message = event.get("message")
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        last_assistant = message
                if event.get("type") == "agent_settled":
                    result["status"] = "settled"
                    result["termination"] = "normal"
                    if "stopReason" in last_assistant:
                        result["model_stop_reason"] = last_assistant["stopReason"]
                    if last_assistant.get("stopReason") == "error":
                        result["status"] = "run_error"
                        result["error"] = last_assistant.get("errorMessage") or "Model inference failed."
                    break
            if backend is not None:
                backend.check_alive()
            if game is not None:
                game.close()
                if game.limit_reached.is_set():
                    result["status"] = "action_limit"
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            if result["status"] in ("timeout", "loop_detected"):
                send({"id": "supervisor-abort", "type": "abort"})
                stop_deadline = time.monotonic() + grace_seconds
                result["termination"] = "forced"
                while True:
                    event = receive(stop_deadline)
                    if event is None:
                        break
                    if (
                        event.get("type") == "response"
                        and event.get("id") == "supervisor-abort"
                        and event.get("success")
                    ):
                        result["termination"] = "graceful"
                        break
    except (OSError, RuntimeError) as exc:
        if result["prompt_submitted_at_utc"]:
            result["status"] = "run_error"
        result["termination"] = "forced"
        result["error"] = str(exc)
    except KeyboardInterrupt:
        result["status"] = "interrupted"
        result["termination"] = "forced"
    finally:
        if game is not None:
            game.close()
            if game.limit_reached.is_set():
                result["status"] = "action_limit"
                result["termination"] = "forced"
                if stop_at_limit is not None and not stop_at_limit():
                    result["immediate_container_stop"] = "failed"
            elif game.failed.is_set() and result["prompt_submitted_at_utc"]:
                result["status"] = "run_error"
                result["termination"] = "forced"
                result["error"] = "Sokoban game service failed."
        if process:
            if process.poll() is None:
                if result["termination"] in ("normal", "graceful"):
                    try:
                        process.stdin.close()
                        process.wait(timeout=grace_seconds)
                    except (OSError, subprocess.TimeoutExpired):
                        result["termination"] = "forced"
                if process.poll() is None:
                    # The bootstrap may not have joined the job yet.
                    process.kill()
                    checked(dll.TerminateJobObject(job, 1))
                    process.wait(timeout=grace_seconds)
            checked(dll.TerminateJobObject(job, 1))
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if reader:
                reader.join(timeout=grace_seconds)
            if process.stdout:
                process.stdout.close()
            result["launcher_exit_code"] = process.returncode
        checked(dll.CloseHandle(job))
        if game is not None:
            result["game"] = game.summary()
        result["ended_at_utc"] = utc_now()
        outcome_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def backend_paths(config_path: Path, server: Path | None, model: Path | None) -> tuple[Path, Path]:
    if server is not None and model is not None:
        return server, model
    try:
        with config_path.open("rb") as file:
            config = tomllib.load(file)
    except FileNotFoundError:
        config = {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Cannot read {config_path}: {exc}") from exc
    paths = []
    for supplied, name in ((server, "llama_server"), (model, "model_file")):
        value = supplied if supplied is not None else config.get(name)
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError(f"Set {name} in {config_path} or pass its command-line option")
        paths.append(Path(value))
    return paths[0], paths[1]


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--job-bootstrap":
        return bootstrap(sys.argv[2], sys.argv[3:])
    parser = argparse.ArgumentParser(
        description="Run one Pi task with an external wall-clock limit."
    )
    parser.add_argument("--limit-seconds", type=float, default=2700)
    parser.add_argument("--thinking", choices=("high", "off"), default="high")
    parser.add_argument("--task", choices=("profile", "sokoban"), default="profile")
    parser.add_argument("--puzzle", choices=("one-push", "align", "baseline", "offset"), default="baseline")
    parser.add_argument("--llama-server", type=Path, help="Override llama_server in config.toml")
    parser.add_argument("--model-file", type=Path, help="Override model_file in config.toml")
    args = parser.parse_args()
    if args.task != "sokoban" and args.puzzle != "baseline":
        parser.error("--puzzle requires --task sokoban")
    if not math.isfinite(args.limit_seconds) or args.limit_seconds <= 0:
        parser.error("--limit-seconds must be a positive finite number")
    try:
        args.llama_server, args.model_file = backend_paths(ROOT / "config.toml", args.llama_server, args.model_file)
    except ValueError as exc:
        parser.error(str(exc))
    run_dir = ROOT / "supervisor-runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True, exist_ok=False)
    print(f"Run records: {run_dir}", flush=True)
    name = "long-horizon-" + uuid.uuid4().hex
    game = backend = guard = None
    agent_launched = False
    model_info = {}
    result = {"status": "startup_error", "termination": None, "limit_seconds": args.limit_seconds,
              "launched_at_utc": utc_now(), "prompt_submitted_at_utc": None}
    limit_cleanup = limit_backend_cleanup = None

    def stop_at_limit() -> bool:
        nonlocal limit_cleanup, limit_backend_cleanup
        limit_cleanup = container_run.cleanup_container(name)
        try:
            limit_backend_cleanup = backend.close()
        except OSError:
            limit_backend_cleanup = False
        return limit_cleanup

    try:
        source = WORKSPACE if args.task == "profile" else ROOT / "sokoban_workspace"
        workspace = container_run.prepare_workspace(source, run_dir, require_agents=args.task == "profile")
        if args.task == "sokoban":
            (workspace / "output").mkdir()
        assignment = (workspace / "task.prompt").read_text(encoding="utf-8")
        if not assignment.strip():
            raise ValueError("task.prompt is empty.")
        if args.task == "sokoban":
            rules_path = workspace / "src" / "sokoban.py"
            game = SokobanAuthority(run_dir, rules_path, puzzle_id=args.puzzle)
            assignment = assignment.replace("{ACTION_LIMIT}", str(game.state["action_limit"]))
            (workspace / "task.prompt").write_text(assignment, encoding="utf-8")
            rules_path.unlink()
        backend = llamacpp_model.LlamaServer(args.llama_server, args.model_file, run_dir)
        model_info = backend.start()
        model_info["thinking"] = args.thinking == "high"
        model_info["thinking_level"] = args.thinking
        model_info["thinking_mapping"] = {"enable_thinking": args.thinking == "high"}
        image_id = network_guard.resolve_image(container_run.IMAGE)
        model_info["container_image_id"] = image_id
        (run_dir / "model.json").write_text(json.dumps(model_info, indent=2) + "\n", encoding="utf-8")
        token = container_run.new_token()
        guard = network_guard.GatewaySession(
            name, token, str(backend.model), args.thinking, game=game,
            backend_token=backend.token, image=image_id,
        )
        guard.start()
        command = container_run.container_command(workspace, name, guard.network, token, args.thinking, image=image_id)
        print(f"Waiting for Pi in Docker; task time limit: {args.limit_seconds:g} seconds.", flush=True)
        agent_launched = True
        result = supervise(command, PROMPT + assignment, args.limit_seconds, run_dir,
                           game=game, stop_at_limit=stop_at_limit, backend=backend)
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
        print(f"Experiment failed: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        result.update(status="interrupted", termination="forced")
    finally:
        if game is not None:
            game.close()
        cleanups = []
        if agent_launched and limit_cleanup is not True:
            cleanups.append(("container_cleanup", lambda: container_run.cleanup_container(name)))
        if backend is not None:
            cleanups.append(("backend_cleanup", backend.close))
        if guard is not None:
            cleanups.append(("gateway_cleanup", guard.close))
        for label, cleanup in cleanups:
            try:
                if not cleanup():
                    result[label] = "failed"
            except (OSError, RuntimeError, subprocess.SubprocessError):
                result[label] = "failed"
        if limit_backend_cleanup is False:
            result["immediate_backend_stop"] = "failed"
        if backend is not None:
            model_info.update(backend.info)
            model_info["verification_complete"] = "allocated_context" in model_info
            (run_dir / "model.json").write_text(json.dumps(model_info, indent=2) + "\n", encoding="utf-8")
        if game is not None:
            result["game"] = game.summary()
        result.setdefault("ended_at_utc", utc_now())
        (run_dir / "outcome.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    cleanup_ok = not any(result.get(key) == "failed" for key in ("container_cleanup", "gateway_cleanup", "backend_cleanup"))
    return 0 if result["status"] == "settled" and cleanup_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
