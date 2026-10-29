import argparse
import ctypes
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "experiment_workspace"
MODEL = "unsloth/Qwen3.5-0.8B-GGUF"
CONTEXT_LENGTH = 128_000
REPEAT_PENALTY = 1.15
PROMPT = "Read task.prompt and complete the assignment described there. Use the current directory as your working directory."


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_operations",
            "write_operations",
            "other_operations",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


def kernel32() -> Any:
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    dll.CreateJobObjectW.restype = wintypes.HANDLE
    dll.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    dll.AssignProcessToJobObject.restype = wintypes.BOOL
    dll.SetHandleInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    dll.SetHandleInformation.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    dll.GetCurrentProcess.restype = wintypes.HANDLE
    dll.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dll.SetInformationJobObject.restype = wintypes.BOOL
    dll.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    dll.TerminateJobObject.restype = wintypes.BOOL
    return dll


def checked(result: Any) -> Any:
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def bootstrap(handle: str, command: list[str]) -> int:
    dll = kernel32()
    handle = wintypes.HANDLE(int(handle))
    checked(dll.AssignProcessToJobObject(handle, dll.GetCurrentProcess()))
    checked(dll.CloseHandle(handle))
    print(json.dumps({"type": "supervisor_bootstrap_ready"}), flush=True)
    return subprocess.call(command)


def supervise(
    command: list[str],
    prompt: str,
    limit_seconds: float,
    run_dir: Path,
    grace_seconds: float = 5,
    startup_seconds: float = 60,
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
    job = checked(dll.CreateJobObjectW(None, None))
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # Close the job if the supervisor crashes.
    checked(
        dll.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
    )
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

            def receive(deadline):
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    try:
                        line = pending.get(timeout=remaining)
                    except queue.Empty:
                        return None
                    if line is None:
                        raise RuntimeError("Agent exited before the operation settled.")
                    try:
                        record = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
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
            while True:
                event = receive(deadline)
                if event is None:
                    result["status"] = "timeout"
                    break
                if (
                    event.get("type") == "response"
                    and event.get("id") == "supervisor-prompt"
                    and not event.get("success")
                ):
                    raise RuntimeError("Pi rejected the prompt.")
                if event.get("type") == "agent_settled":
                    result["status"] = "settled"
                    result["termination"] = "normal"
                    break
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            if result["status"] == "timeout":
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
        if result["status"] == "startup_error" and result["prompt_submitted_at_utc"]:
            result["status"] = "run_error"
        result["error"] = str(exc)
    except KeyboardInterrupt:
        result["status"] = "interrupted"
        result["termination"] = "forced"
    finally:
        if process:
            if process.poll() is None:
                if result["termination"] in ("normal", "graceful"):
                    try:
                        process.stdin.close()
                        process.wait(timeout=grace_seconds)
                    except (OSError, subprocess.TimeoutExpired):
                        result["termination"] = "forced"
                if process.poll() is None:
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
        result["ended_at_utc"] = utc_now()
        outcome_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--job-bootstrap":
        return bootstrap(sys.argv[2], sys.argv[3:])
    parser = argparse.ArgumentParser(
        description="Run one Pi task with an external wall-clock limit."
    )
    parser.add_argument("--limit-seconds", type=float, default=2700)
    args = parser.parse_args()
    if not math.isfinite(args.limit_seconds) or args.limit_seconds <= 0:
        parser.error("--limit-seconds must be a positive finite number")
    run_dir = (
        ROOT
        / "supervisor-runs"
        / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    command = [
        "unsloth",
        "start",
        "pi",
        "--persist",
        "--no-serve",
        "--model",
        MODEL,
        "--context-length",
        str(CONTEXT_LENGTH),
        "--repeat-penalty",
        str(REPEAT_PENALTY),
        "--mode",
        "rpc",
        "--session-dir",
        str(run_dir / "pi-sessions"),
    ]
    print(f"Run records: {run_dir}", flush=True)
    print(
        f"Waiting for Pi; time limit after prompt submission: {args.limit_seconds:g} seconds.",
        flush=True,
    )
    result = supervise(command, PROMPT, args.limit_seconds, run_dir)
    print(json.dumps(result, indent=2), flush=True)
    if result["status"] == "startup_error":
        print(
            "Pi did not start. Check that Unsloth Studio is running with a model loaded and pi is on PATH.",
            file=sys.stderr,
        )
    return 0 if result["status"] == "settled" else 1


if __name__ == "__main__":
    raise SystemExit(main())
