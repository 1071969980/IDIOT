#!/bin/bash
# 激活虚拟环境并启动服务
source .venv/bin/activate
echo "Starting server..."
# 打印当前目录
echo "Current directory: $(pwd)"
# 如果 API_DEBUG 为 不为 0 则使用uvicorn启动服务
if [ "$API_DEBUG" != "0" ]; then
    echo "Using uvicorn to start server..."
    uvicorn api.app.main:app --host 0.0.0.0 --port 8000
else
    echo "Using gunicorn to start server..."
    gunicorn api.app.main:app \
        --workers 4 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --log-level debug
fi