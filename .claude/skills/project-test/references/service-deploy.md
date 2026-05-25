# Kubernetes 服务部署

## 命名空间结构

| 命名空间 | 服务数量 | 包含的服务 |
|---------|---------|-----------|
| `idiot` | 10 | api, git-server, postgres, redis, minio, nginx, prometheus, otel-collector, app-notification, user-pod-scheduler |
| `idiot-user-space-storage` | 2 | juicefs-minio, juicefs-postgres |

## 镜像与 Deployment 映射（关键）

| 镜像 | 使用的 Deployment | 说明 |
|------|------------------|------|
| `idiot-api` | api, app-notification, user-pod-scheduler, git-server | git-server 使用同一镜像但入口点不同 |
| `idiot-git-server` | git-server | git-server 专用镜像 |

**重点：** `idiot-api` 镜像被 4 个 Deployment 共用。当 `idiot-api` 镜像重新构建后，所有 4 个 Deployment 都需要重启：

```bash
kubectl rollout restart deployment/api deployment/app-notification deployment/user-pod-scheduler deployment/git-server -n idiot
```

## 集群健康检查

```bash
kubectl get all -n idiot
kubectl get all -n idiot-user-space-storage
```

判断标准：
- 所有 Pod 状态为 Running
- Ready 列显示 1/1（或对应期望副本数）
- RESTARTS 为 0 或接近 0

## 服务重启（滚动更新）

```bash
# 重启指定 Deployment
kubectl rollout restart deployment/<name> -n <namespace>

# 等待滚动更新完成
kubectl rollout status deployment/<name> -n <namespace>
```

**优先使用 `rollout restart`，不要使用 `kubectl delete pod`：**
- 零停机：新 Pod 先启动，旧 Pod 再终止
- 可通过 `rollout status` 查看进度
- 可通过 `rollout undo` 回滚

## 调试模式（ConfigMap）

ConfigMap 名称：`idiot-config`，位于 `idiot` 命名空间。

| 配置项 | 说明 |
|-------|------|
| `API_DEBUG: "1"` | 启用调试模式 |
| `API_DEBUG_PORT: "5678"` | debugpy 监听端口 |

**调试模式行为：**
- 3 个服务支持 debugpy：api、app-notification、user-pod-scheduler
- 启用调试模式后，服务在 `debugpy.wait_for_client()` 处阻塞，等待调试器连接后才会继续启动
- 调试模式使用 uvicorn（1 worker），生产模式使用 gunicorn（4 worker）
- 这意味着 `rollout restart` 后，服务不会实际处理请求，直到调试器连接

## 端口转发（使用 Service 而非 Pod）

```bash
# 通过 Service 转发（推荐，Pod 重启后连接不断）
kubectl port-forward -n idiot svc/api 5678:5678 &
kubectl port-forward -n idiot svc/app-notification 5679:5678 &
kubectl port-forward -n idiot svc/user-pod-scheduler 5680:5678 &

# 通过 nginx 访问服务 API
kubectl port-forward -n idiot svc/nginx 8143:8143 &
```

**务必使用 `svc/` 而非 `pod/`：** Pod 名称在重启后会改变，使用 Service 可以避免重新查询 Pod 名称。

## Kubernetes 服务端口

| Service | 端口 | 用途 |
|---------|------|------|
| api | 8000 (app), 5678 (debug) | 主 API 服务 |
| app-notification | 8001 (app), 5678 (debug) | 通知服务 |
| user-pod-scheduler | 8001 (app), 5678 (debug) | Pod 调度器 |
| git-server | 22 | SSH / Gitolite |
| nginx | 8143 | 反向代理（外部访问入口） |
| postgres | 5432 | 数据库 |
| redis | 6379 | 缓存 |
| minio | 9000 / 9001 | 对象存储 |

## 镜像重建后的完整启动流程

```
1. 检查集群健康：
   kubectl get all -n idiot && kubectl get all -n idiot-user-space-storage

2. 重启受影响的 Deployment：
   kubectl rollout restart deployment/api deployment/app-notification deployment/user-pod-scheduler deployment/git-server -n idiot

3. 等待滚动更新完成：
   kubectl rollout status deployment/api -n idiot
   kubectl rollout status deployment/app-notification -n idiot
   kubectl rollout status deployment/user-pod-scheduler -n idiot
   kubectl rollout status deployment/git-server -n idiot

4. （调试模式下）转发调试端口：
   kubectl port-forward -n idiot svc/api 5678:5678 &
   kubectl port-forward -n idiot svc/app-notification 5679:5678 &
   kubectl port-forward -n idiot svc/user-pod-scheduler 5680:5678 &

5. （调试模式下）连接调试器解除阻塞：
   参见 [debug-attach.md](debug-attach.md)

6. 验证服务可用：
   kubectl port-forward -n idiot svc/nginx 8143:8143 &
   curl https://localhost:8143/health  # 或对应的健康检查端点
```
