# 应用部署配置

## 应用启动入口

文件位置：`api/app/system_notification_app.py`

参照 `api/app/user_pod_scheduler_app.py` 的模式：

```python
from api.core.env_config import debug_config

DEBUG = debug_config.api_debug
if DEBUG:
    import debugpy
    DEBUG_PORT = debug_config.api_debug_port
    debugpy.listen(("0.0.0.0", DEBUG_PORT))
    debugpy.wait_for_client()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.redis.distributed_lock import distributed_lock
from api.app.graceful_shutdown import wait_background_task_for_graceful_shutdown
from api.app.system_notification.router_declare import router
from api.logger import init_logger


# 分布式锁保护数据库初始化：这是对主应用 @distributed_lock("init_postgres_db") 模式的
# 借鉴与改进（User Pod Scheduler 应用未使用此模式），在多 worker 场景下提供更好的保护。
@distributed_lock("init_notification_db")
async def init_db():
    from api.system_notification.sql_stat.system_notification.utils import create_table as ct1
    from api.system_notification.sql_stat.system_notification_ack.utils import create_table as ct2
    from api.system_notification.sql_stat.user_notification.utils import create_table as ct3
    from api.system_notification.sql_stat.session_notification.utils import create_table as ct4
    await ct1()
    await ct2()
    await ct3()
    await ct4()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing notification database...")
    await init_db()
    init_logger()
    yield
    await wait_background_task_for_graceful_shutdown()


app = FastAPI(
    title="System Notification",
    root_path="/system-notification",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(router)
```

## 启动脚本

文件位置：`api/system_notification_app.sh`

参照 `api/run.sh` 模式：

```bash
#!/bin/bash
source .venv/bin/activate
echo "Starting system notification server..."
if [ "$API_DEBUG" != "0" ]; then
    uvicorn api.app.system_notification_app:app --host 0.0.0.0 --port 8001
else
    gunicorn api.app.system_notification_app:app \
        --workers 2 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8001 \
        --log-level debug \
        --forwarded-allow-ips='*'
fi
```

## K8s部署配置

### 读取服务

文件位置：`k8s/base/12.2-system-notification-api.yaml`

参照 `k8s/base/12.1-user-pod-scheduler.yaml`，公告服务不需要 RBAC 权限（无 K8s 资源操作），配置更简单。

```yaml
# System Notification API Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: system-notification
  namespace: idiot
  labels:
    app: system-notification
spec:
  replicas: 1
  selector:
    matchLabels:
      app: system-notification
  template:
    metadata:
      labels:
        app: system-notification
    spec:
      containers:
        - name: system-notification
          image: idiot-api:latest
          imagePullPolicy: IfNotPresent
          workingDir: /app
          command: ["./api/system_notification_app.sh"]
          envFrom:
            - configMapRef:
                name: idiot-config
            - secretRef:
                name: idiot-secrets
          ports:
            - containerPort: 8001
              name: http
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "1Gi"
              cpu: "500m"
---
# System Notification Service
apiVersion: v1
kind: Service
metadata:
  name: system-notification
  namespace: idiot
spec:
  selector:
    app: system-notification
  ports:
    - name: http
      port: 8001
      targetPort: 8001
```

### Task Pod

文件位置：`k8s/base/12.3-system-notification-task.yaml`

使用 CronJob 控制器，可通过 `kubectl create job --from` 手动触发一次性执行。

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: system-notification-task
  namespace: idiot
spec:
  schedule: "0 0 31 2 *"  # 永不自动触发（2月31日不存在），仅手动触发
  suspend: true            # 额外保护：禁止自动调度
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: task
              image: idiot-api:latest
              imagePullPolicy: IfNotPresent
              workingDir: /app
              command: ["./api/system_notification_task.sh"]
              args: ["--level", "info", "--content", "placeholder"]
              envFrom:
                - configMapRef:
                    name: idiot-config
                - secretRef:
                    name: idiot-secrets
              resources:
                requests:
                  memory: "128Mi"
                  cpu: "50m"
                limits:
                  memory: "256Mi"
                  cpu: "200m"
```

手动创建公告示例：

```bash
kubectl create job manual-notif-$(date +%s) --from=cronjob/system-notification-task -- \
    --level warning --content "系统将于今晚22:00维护"
```

创建后需在 `k8s/base/kustomization.yaml` 中添加引用：

```yaml
- 12.2-system-notification-api.yaml
- 12.3-system-notification-task.yaml
```
