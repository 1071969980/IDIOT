#!/usr/bin/env python3
"""
Session stream chat view — /chat/session_streaming

Receives chat.* events from the session-level SSE stream.

Usage:
  python sse_chat.py --username USER --session-id SID [options]
  python sse_chat.py --token TOKEN   --session-id SID [options]

Options:
  --base-url URL       (default: http://localhost:8143/api)
  --password PASS      (default: password_test, 配合 --username)
  --output-dir DIR     Save formatted + raw logs
  --last-event-id ID   Resume from this event ID
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _sse_lib import add_auth_args, format_chat, resolve_token, run_stream


def main():
    p = argparse.ArgumentParser(description="Chat streaming viewer")
    p.add_argument("--base-url", default="http://localhost:8143/api")
    add_auth_args(p)
    p.add_argument("--session-id", required=True)
    p.add_argument("--output-dir")
    p.add_argument("--last-event-id")
    args = p.parse_args()

    token = resolve_token(args)
    run_stream(
        name="chat",
        endpoint="/chat/session_streaming",
        body={"session_id": args.session_id},
        formatter=format_chat,
        args=args,
        token=token,
    )


if __name__ == "__main__":
    main()
