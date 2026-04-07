#!/bin/bash
# 激活虚拟环境并启动系统公告读取服务
source .venv/bin/activate
echo "Starting system notification server..."
if [ "$API_DEBUG" != "0" ]; then
    echo "Using uvicorn to start server..."
    uvicorn api.app.system_notification_app:app --host 0.0.0.0 --port 8001
else
    echo "Using gunicorn to start server..."
    gunicorn api.app.system_notification_app:app \
        --workers 2 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8001 \
        --log-level debug \
        --forwarded-allow-ips='*'
fi
