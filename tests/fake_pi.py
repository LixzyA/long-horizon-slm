import json
import os
import subprocess
import sys
import time

mode = sys.argv[1]
print(json.dumps({"type": "test_cwd", "cwd": os.getcwd()}), flush=True)
if mode == "exit":
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
        if mode == "complete":
            print(json.dumps({"type": "agent_settled"}), flush=True)
    elif request["type"] == "abort" and mode == "abort":
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
    elif request["type"] == "abort" and mode == "hang":
        time.sleep(60)
