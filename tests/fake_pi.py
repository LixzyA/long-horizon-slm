import json
import os
import subprocess
import sys
import time

mode = sys.argv[1]
print(json.dumps({"type": "test_cwd", "cwd": os.getcwd()}), flush=True)
if mode == "invalid_startup":
    print(sys.argv[2], flush=True)
if mode == "exit":
    print("launcher: test startup failure", file=sys.stderr, flush=True)
    raise SystemExit(2)
if mode == "hang":
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    print(json.dumps({"type": "test_child", "pid": child.pid}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if request["type"] == "get_state":
        print(
            json.dumps(
                {
                    "type": "response",
                    "command": "get_state",
                    "id": request["id"],
                    "success": True,
                }
            ),
            flush=True,
        )
    elif request["type"] == "prompt":
        print(
            json.dumps(
                {
                    "type": "response",
                    "command": "prompt",
                    "id": request["id"],
                    "success": True,
                    "data": {"disposition": "started"},
                }
            ),
            flush=True,
        )
        if mode == "crash":
            raise SystemExit(3)
        if mode == "invalid_runtime":
            print(sys.argv[2], flush=True)
        if mode in ("model_error", "model_error_recovered"):
            print(json.dumps({
                "type": "message_end", "message": {
                    "role": "assistant", "stopReason": "error", "errorMessage": "503 model unavailable",
                },
            }), flush=True)
        if mode in ("complete", "loop", "loop_hang", "model_error_recovered"):
            print(
                json.dumps(
                    {
                        "type": "message_update",
                        "assistantMessageEvent": {
                            "type": "toolcall_delta",
                            "delta": "partial",
                        },
                    }
                ),
                flush=True,
            )
            print(
                json.dumps(
                    {
                        "type": "tool_execution_update",
                        "partialResult": {"text": "partial"},
                    }
                ),
                flush=True,
            )
            print(
                json.dumps(
                    {
                        "type": "message_end",
                        "message": {"role": "assistant", "content": "complete", "stopReason": "stop"},
                    }
                ),
                flush=True,
            )
        if mode in ("loop", "loop_hang"):
            for i in range(10):
                call_id = str(i)
                print(
                    json.dumps(
                        {
                            "type": "tool_execution_start",
                            "toolCallId": call_id,
                            "toolName": "bash",
                            "args": {"command": "bad"},
                        }
                    ),
                    flush=True,
                )
                print(
                    json.dumps(
                        {
                            "type": "tool_execution_end",
                            "toolCallId": call_id,
                            "toolName": "bash",
                            "isError": True,
                            "result": {"text": "failure"},
                        }
                    ),
                    flush=True,
                )
        if mode in ("complete", "model_error", "model_error_recovered"):
            print(json.dumps({"type": "agent_settled"}), flush=True)
    elif request["type"] == "abort" and mode in ("abort", "loop"):
        print(
            json.dumps(
                {
                    "type": "response",
                    "command": "abort",
                    "id": request["id"],
                    "success": True,
                }
            ),
            flush=True,
        )
        break
    elif request["type"] == "abort" and mode in ("hang", "loop_hang"):
        time.sleep(60)
