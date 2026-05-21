#!/usr/bin/env python3
"""
Message history renderer for IDIOT project.

Fetches session message history and renders it in a readable format,
consistent with sse_chat.py output style.

Usage:
  python message_history.py --username USER --session-id SID [options]
  python message_history.py --token TOKEN   --session-id SID [options]

Options:
  --base-url URL       (default: http://localhost:8143/api)
  --password PASS      (default: password_test, 配合 --username)
  --branch NAME        Branch name (default: main)
  --limit N            Limit number of messages
  --output FILE        Write to file instead of stdout
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _sse_lib import add_auth_args, resolve_token

import requests


def format_user_msg(msg):
    seq = msg.get("seq_index", "?")
    status = msg.get("status", "?")
    content = msg.get("content", "")
    ts = msg.get("created_at", "")[:19].replace("T", " ")
    task = msg.get("session_task_id", "")
    task_str = f"  task={task[:8]}…" if task else ""
    return f"[User #{seq}] ({ts}) [{status}]{task_str}\n  {content}"


def format_agent_msg(msg):
    sub = msg.get("sub_seq_index", "?")
    status = msg.get("status", "?")
    content = msg.get("content", "")
    ts = msg.get("created_at", "")[:19].replace("T", " ")
    task = msg.get("session_task_id", "")
    task_str = f"  task={task[:8]}…" if task else ""
    json_content = msg.get("json_content")

    lines = [f"[Assistant #{sub}] ({ts}) [{status}]{task_str}"]
    lines.append(f"  ▸ {content}")
    if json_content:
        lines.append(f"  (json: {json.dumps(json_content, ensure_ascii=False)})")
    return "\n".join(lines)


FORMATTERS = {
    "user": format_user_msg,
    "assistant": format_agent_msg,
}


def main():
    p = argparse.ArgumentParser(description="Message history renderer")
    p.add_argument("--base-url", default="http://localhost:8143/api")
    add_auth_args(p)
    p.add_argument("--session-id", required=True)
    p.add_argument("--branch", default="main")
    p.add_argument("--limit", type=int)
    p.add_argument("--output", "-o", help="Write to file instead of stdout")
    args = p.parse_args()

    token = resolve_token(args)

    headers = {
        "Content-Type": "application/json",
        "Cookie": f"auth_token={token}",
    }
    body = {"session_id": args.session_id, "branch_name": args.branch}
    if args.limit:
        body["limit"] = args.limit

    resp = requests.post(
        f"{args.base_url}/chat/sessions/messages_history",
        json=body, headers=headers,
    )
    if resp.status_code != 200:
        print(f"[ERROR] HTTP {resp.status_code}: {resp.text[:200]}",
              file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    messages = data.get("messages", [])

    # Render
    lines = []
    lines.append("=" * 60)
    lines.append(f"Session: {args.session_id}")
    lines.append(f"Branch:  {args.branch}")
    lines.append(f"Messages: {len(messages)}")
    lines.append("=" * 60)
    lines.append("")

    for item in messages:
        role = item["role"]
        msg = item["message"]
        fn = FORMATTERS.get(role)
        if fn:
            lines.append(fn(msg))
        else:
            lines.append(f"[{role}] {json.dumps(msg, ensure_ascii=False)}")
        lines.append("")

    lines.append(f"--- {len(messages)} messages ---")

    output = "\n".join(lines)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
