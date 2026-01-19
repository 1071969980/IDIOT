#!/bin/bash
# LSP 参数验证脚本
# 用法: bash verify_lsp_params.sh <file> <line> <symbol>
# 输出: file:line:character

file="$1"
line="$2"
symbol="$3"

if [ $# -lt 3 ]; then
    echo "Usage: bash verify_lsp_params.sh <file> <line> <symbol>" >&2
    exit 1
fi

if [ ! -f "$file" ]; then
    echo "Error: File '$file' not found" >&2
    exit 1
fi

# 获取行内容
content=$(sed -n "${line}p" "$file")

if [ -z "$content" ]; then
    echo "Error: Line $line is empty or out of range" >&2
    exit 1
fi

# 计算 character 位置
char_pos=$(python3 -c "
line = '''$content'''
symbol = '$symbol'
try:
    print(line.index(symbol) + 1)
except ValueError:
    exit(1)
" 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "Error: Symbol '$symbol' not found in line $line" >&2
    exit 1
fi

# 输出: file:line:character
echo "$file:$line:$char_pos"
