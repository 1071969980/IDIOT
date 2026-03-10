#!/bin/bash
# 激活虚拟环境并启动用户 Pod 调度器服务
source .venv/bin/activate
echo "Starting user pod scheduler..."
echo "Current directory: $(pwd)"

# 如果 API_DEBUG 不为 0 则使用 uvicorn 启动服务
if [ "$API_DEBUG" != "0" ]; then
    echo "Using uvicorn to start server..."
    uvicorn api.app.user_pod_scheduler_app:app --host 0.0.0.0 --port 8001
else
    echo "Using gunicorn to start server..."
    gunicorn api.app.user_pod_scheduler_app:app \
        --workers 2 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8001 \
        --log-level debug \
        --forwarded-allow-ips='*'
fi