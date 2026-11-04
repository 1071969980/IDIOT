"""Shared SSE parsing, formatting, and connection logic.

Imported by sse_chat.py, sse_events.py, sse_hil.py, message_history.py.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Authentication —参照 api-auth.md
# ---------------------------------------------------------------------------

def login(base_url, username, password):
    """登录获取 auth_token。参照 api-auth.md 的 Secure Cookie 说明，
    K8s nginx 为 HTTP，需手动提取 token。"""
    resp = requests.post(
        f"{base_url}/auth/token",
        data={"username": username, "password": password},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"登录失败: HTTP {resp.status_code} {resp.text[:200]}")
    token = resp.cookies.get("auth_token")
    if not token:
        raise RuntimeError("登录响应中无 auth_token cookie")
    return token


def add_auth_args(parser):
    """为 argparse 添加统一的认证参数。"""
    auth = parser.add_mutually_exclusive_group(required=True)
    auth.add_argument("--token", help="直接传入 auth_token（跳过登录）")
    auth.add_argument("--username", help="用户名（自动登录获取 token）")
    parser.add_argument("--password", default="password_test",
                        help="密码（配合 --username，默认: password_test）")


def resolve_token(args):
    """从 args 中获取 token：直接使用或通过登录获取。"""
    if args.token:
        return args.token
    print(f"[{ts()}] 登录中... ", end="", flush=True)
    token = login(args.base_url, args.username, args.password)
    print(f"ok", flush=True)
    return token


# ---------------------------------------------------------------------------
# SSE protocol parser
# ---------------------------------------------------------------------------

def iter_sse_events(response):
    """Yield (event_type, data_str, event_id) from a streaming response.

    Comment-only frames are yielded with event_type ``comment`` so callers can
    distinguish ``heartbeat`` from ``cursor-expired``.
    """
    event_type = None
    data_parts = []
    event_id = ""
    comment = None

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue

        if raw_line.startswith("event:"):
            event_type = raw_line[6:].strip()
        elif raw_line.startswith("data:"):
            data_parts.append(raw_line[5:].strip())
        elif raw_line.startswith("id:"):
            event_id = raw_line[3:].strip()
        elif raw_line.startswith("retry:"):
            pass
        elif raw_line.startswith(":"):
            comment = raw_line[1:].strip()
        elif raw_line == "":
            if comment is not None:
                yield "comment", comment, ""
            elif event_type is not None or data_parts:
                yield event_type or "message", "\n".join(data_parts), event_id
            event_type = None
            data_parts = []
            event_id = ""
            comment = None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def short_id(uid, n=8):
    return uid[:n] + "…" if uid and len(uid) > n else uid


# ---------------------------------------------------------------------------
# Per-stream formatters
# ---------------------------------------------------------------------------

def _parse_envelope(event_type, data_str):
    if event_type == "init":
        return "connected", None
    if event_type == "comment":
        if data_str == "heartbeat":
            return "♥", None
        if data_str == "cursor-expired":
            return "⚠ cursor expired: 从当前可读窗口继续", None
        return f"[comment] {data_str}", None
    try:
        return None, json.loads(data_str)
    except json.JSONDecodeError:
        return f"[{event_type}] {data_str}", None


def format_chat(event_type, data_str):
    text, obj = _parse_envelope(event_type, data_str)
    if text is not None:
        return text
    if event_type == "chat.text_msg_delta":
        return f"▸ {obj.get('payload', {}).get('content', '')}"
    if event_type == "chat.reasoning_delta":
        return f"… reasoning: {obj.get('payload', {}).get('content', '')}"
    if event_type == "chat.text_msg_begin":
        return "▷ text begin"
    if event_type == "chat.text_msg_end":
        return "■ text end"
    if event_type == "chat.stream_end":
        payload = obj.get("payload", {})
        return f"■ chat ended | outcome={payload.get('outcome')} error={payload.get('error')}"
    if event_type in ("chat.tool_call", "chat.tool_response"):
        return f"[{event_type}] {json.dumps(obj.get('payload', {}), ensure_ascii=False)}"
    return f"[{event_type}] {json.dumps(obj, ensure_ascii=False)}"


def format_session_event(event_type, data_str):
    text, obj = _parse_envelope(event_type, data_str)
    if text is not None:
        return text
    payload = obj.get("payload", {})
    task = short_id(obj.get("session_task_id", ""))
    branch = obj.get("branch_name") or "?"
    if event_type == "session.branch_task_started":
        return f"▶ task started  | branch={branch}  task={task}"
    if event_type == "session.branch_task_completed":
        return (
            f"■ task finished | branch={branch}  task={task}  "
            f"outcome={payload.get('outcome')}  "
            f"{'✗ exception' if payload.get('has_exception') else '✓'}"
        )
    return f"[{event_type}] {json.dumps(obj, ensure_ascii=False)}"


def format_hil(event_type, data_str):
    text, obj = _parse_envelope(event_type, data_str)
    if text is not None:
        return text
    if event_type == "hil.stream_end":
        return "■ HIL channel ended"

    payload = obj.get("payload", {})
    content = payload.get("content", {})
    body = content.get("body", {}) if isinstance(content, dict) else {}
    tool_name = body.get("tool_name", "?")
    body_type = body.get("type", "?")
    detail = body.get("detail", {})

    if event_type == "hil.HIL_interrupt_request":
        lines = [f"✋ interrupt | tool={tool_name}  type={body_type}  msg_id={payload.get('msg_id')}"]
        if body_type == "ChoiceForm" and isinstance(detail, dict):
            lines.append(f"  question: {detail.get('question', '')}")
            lines.append(f"  options:  {detail.get('options', [])}")
            if detail.get("allow_additional_input"):
                lines.append("  (custom input allowed)")
        elif isinstance(detail, dict) and detail:
            for k, v in detail.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    if event_type == "hil.Notification":
        return f"📢 notify | tool={tool_name}  type={body_type}  msg_id={payload.get('msg_id')}\n  {json.dumps(detail, ensure_ascii=False)}"

    return f"[{event_type}] {json.dumps(obj, ensure_ascii=False)}"


# ---------------------------------------------------------------------------
# Shared runner
# ---------------------------------------------------------------------------

def run_stream(name, endpoint, body, formatter, args, token):
    """Connect to an SSE endpoint, format and print events."""
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"auth_token={token}",
    }
    if args.last_event_id:
        headers["Last-Event-ID"] = args.last_event_id

    url = f"{args.base_url}{endpoint}"

    # Log files
    fmt_file = raw_file = None
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fmt_file = open(out / f"{name}_formatted_{stamp}.log", "w", buffering=1)
        raw_file = open(out / f"{name}_raw_{stamp}.log", "w", buffering=1)

    banner = f"[{ts()}] === {name} stream connected ==="
    print(banner, flush=True)
    if fmt_file:
        fmt_file.write(banner + "\n")

    try:
        resp = requests.post(url, json=body, headers=headers,
                             stream=True, timeout=30)
        if resp.status_code != 200:
            err = f"[{ts()}] HTTP {resp.status_code}: {resp.text[:200]}"
            print(err, file=sys.stderr, flush=True)
            sys.exit(1)

        for event_type, data, eid in iter_sse_events(resp):
            t = ts()
            formatted = formatter(event_type, data)

            for line in formatted.split("\n"):
                out_line = f"[{t}] {line}"
                print(out_line, flush=True)
                if fmt_file:
                    fmt_file.write(out_line + "\n")

            if raw_file:
                raw_file.write(
                    f"[{t}] event:{event_type}\ndata:{data}\nid:{eid}\n\n"
                )

    except KeyboardInterrupt:
        print(f"\n[{ts()}] --- disconnected ---", flush=True)
    except requests.exceptions.ChunkedEncodingError:
        print(f"[{ts()}] --- stream closed by server ---", flush=True)
    except requests.exceptions.ConnectionError as e:
        print(f"[{ts()}] connection error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        for f in (fmt_file, raw_file):
            if f:
                f.close()
