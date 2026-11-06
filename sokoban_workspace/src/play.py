import argparse
import http.client
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Play the supervisor-owned Sokoban game.")
    parser.add_argument("action", choices=("show", "history", "up", "down", "left", "right", "undo"))
    args = parser.parse_args()
    token = os.environ.get("MODEL_PROXY_TOKEN")
    if not token:
        print("Game connection is unavailable.", file=sys.stderr)
        return 1
    connection = http.client.HTTPConnection("gateway", 8080, timeout=35)
    try:
        connection.request(
            "POST", "/sokoban", json.dumps({"action": args.action}),
            {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            print("Game request failed; use show to check the state before retrying.", file=sys.stderr)
            return 1
        print(response.read().decode("utf-8"))
        return 0
    except (OSError, http.client.HTTPException, UnicodeError):
        print("Game connection failed; use show to check the state before retrying.", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
