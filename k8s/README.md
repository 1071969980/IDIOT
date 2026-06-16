# Kubernetes 部署指南

## 文件结构

```
k8s/
├── 00-namespace.yaml        # 命名空间
├── 01-secrets.yaml          # 敏感信息
├── 02-configmap.yaml        # 应用配置
├── 03-pvc.yaml              # 持久化存储 (hostPath)
├── 04-redis.yaml            # Redis
├── 05-postgres.yaml         # PostgreSQL
├── 05.1-juicefs-postgres.yaml  # JuiceFS PostgreSQL (idiot-user-space-storage)
├── 09-minio.yaml            # MinIO 对象存储
├── 09.1-juicefs-minio.yaml  # JuiceFS MinIO (idiot-user-space-storage)
├── 10-prometheus.yaml       # Prometheus 监控
├── 11-otel-collector.yaml   # OpenTelemetry Collector
├── 12-api.yaml              # API 服务
├── 12.1-user-pod-scheduler.yaml  # User Pod 调度器
├── 13-nginx.yaml            # Nginx 反向代理
├── 14-nodeports.yaml        # 外部访问端口
├── 15-host-services.yaml    # 主机上的服务
└── volumes/                 # 数据存储目录 (自动创建)
```

## 前置条件

1. 确保 kubectl 已配置正确的集群上下文
2. 构建所需镜像（见下方说明）

## 构建镜像

部署前需要构建以下镜像：

```bash
# 在项目根目录执行

# 1. 构建 API 镜像
docker build -t idiot-api:latest -f api/Dockerfile .
```

## 部署步骤

### 方式一：按顺序部署

```bash
cd k8s

# 1. 创建命名空间
kubectl apply -f 00-namespace.yaml

# 2. 创建 Secrets（请先修改敏感信息！）
kubectl apply -f 01-secrets.yaml

# 3. 创建 ConfigMap
kubectl apply -f 02-configmap.yaml

# 4. 创建持久化存储
kubectl apply -f 03-pvc.yaml

# 5. 部署基础服务
kubectl apply -f 04-redis.yaml
kubectl apply -f 05-postgres.yaml

# 6. 部署 MinIO
kubectl apply -f 09-minio.yaml

# 8. 部署监控
kubectl apply -f 10-prometheus.yaml
kubectl apply -f 11-otel-collector.yaml

# 9. 部署 API
kubectl apply -f 12-api.yaml

# 10. 部署 Nginx 网关
kubectl apply -f 13-nginx.yaml
kubectl apply -f 14-nodeports.yaml
kubectl apply -f 15-host-services.yaml
```

### 方式二：一键部署

```bash
cd k8s
kubectl apply -f .
```

## 访问服务

| 服务 | 地址 | 说明 |
|------|------|------|
| API 主入口 | http://localhost:30143 | 通过 Nginx 反向代理 |
| Prometheus | http://localhost:30143/prometheus/ | 监控界面 |

## 常用命令

```bash
# 查看所有资源
kubectl get all -n idiot

# 查看 Pod 状态
kubectl get pods -n idiot

# 查看 Pod 详情
kubectl describe pod <pod-name> -n idiot

# 查看日志
kubectl logs -f deployment/api -n idiot

# 进入容器
kubectl exec -it deployment/api -n idiot -- /bin/bash

# 删除所有资源
kubectl delete namespace idiot
```

## 数据存储

数据存储在 `k8s/volumes/` 目录下：

```
k8s/volumes/
├── postgres/              # PostgreSQL 数据
├── redis/                 # Redis 数据
├── minio/                 # MinIO 数据
├── juicefs-minio/         # JuiceFS MinIO 数据 (idiot-user-space-storage)
├── juicefs-postgres-storage/  # JuiceFS PostgreSQL 数据 (idiot-user-space-storage)
├── prometheus/            # Prometheus 数据
└── api/                   # API 应用数据
```

## 注意事项

1. **修改 Secrets**：部署前请修改 `01-secrets.yaml` 中的敏感信息
2. **镜像拉取**：本地构建的镜像使用 `imagePullPolicy: IfNotPresent`
3. **资源限制**：可根据实际需求调整各服务的 `resources`
4. **前端开发**：Nginx 配置中代理到 `host.docker.internal:5173`，需要本地运行前端开发服务器

## 调试用的端口转发

### headlamp (k8s 管理界面)
kubectl port-forward -n kube-system service/my-headlamp 8080:80

### api 服务 debug 端口 （debug 模式下需要连接调试器服务才会正式启动）
kubectl port-forward -n idiot service/api 5678:5678

### user-pod-scheduler 服务 debug 端口 （debug 模式下需要连接调试器服务才会正式启动）
kubectl port-forward -n idiot service/user-pod-scheduler 5679:5678

### minio 服务 管理界面
kubectl port-forward -n idiot service/minio 9001:9001