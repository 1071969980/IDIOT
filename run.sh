#!/bin/bash
# 激活虚拟环境并启动服务
source venv/bin/activate
uvicorn api.app.main:app --host 0.0.0.0 --port 8000