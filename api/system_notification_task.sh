#!/bin/bash
# 激活虚拟环境并运行系统公告 Task Pod
source .venv/bin/activate
python -m api.system_notification_task.task_app "$@"
