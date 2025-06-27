#!/bin/bash
# 激活虚拟环境并启动服务
source .venv/bin/activate
echo "Starting server..."
# 打印当前目录
echo "Current directory: $(pwd)"
# uvicorn api.app.main:app --host 0.0.0.0 --port 8000
gunicorn api.app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --log-level debug