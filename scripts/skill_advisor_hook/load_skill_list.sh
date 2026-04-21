#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# uv 环境安装在 /scripts/，需要从该目录运行
cd /scripts

uv run python "$SCRIPT_DIR/load_skill_list.py"
