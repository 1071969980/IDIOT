#!/usr/bin/env python3
"""
Session events viewer — /session_events/streaming

Monitors task lifecycle events (started/completed) and memory operations.

Usage:
  python sse_events.py --username USER --session-id SID [options]
  python sse_events.py --token TOKEN   --session-id SID [options]

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
from _sse_lib import add_auth_args, format_session_event, resolve_token, run_stream


def main():
    p = argparse.ArgumentParser(description="Session event streaming viewer")
    p.add_argument("--base-url", default="http://localhost:8143/api")
    add_auth_args(p)
    p.add_argument("--session-id", required=True)
    p.add_argument("--output-dir")
    p.add_argument("--last-event-id")
    args = p.parse_args()

    token = resolve_token(args)
    run_stream(
        name="events",
        endpoint="/session_events/streaming",
        body={"session_id": args.session_id},
        formatter=format_session_event,
        args=args,
        token=token,
    )


if __name__ == "__main__":
    main()
