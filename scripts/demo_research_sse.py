from __future__ import annotations

import argparse
import base64
import json
import urllib.request
import sys


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Call the Research SSE conversation endpoint.")
    parser.add_argument("message")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--username", default="student")
    parser.add_argument("--password", default="student123")
    parser.add_argument("--user-id", help="Request user_id; defaults to username.")
    parser.add_argument("--session-id")
    args = parser.parse_args()

    credentials = base64.b64encode(f"{args.username}:{args.password}".encode("utf-8")).decode("ascii")
    payload = json.dumps({
        "user_id": args.user_id or args.username,
        "session_id": args.session_id,
        "message": args.message,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/api/research/chat/stream",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
        },
    )
    with urllib.request.urlopen(request) as response:
        for raw_line in response:
            print(raw_line.decode("utf-8").rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
