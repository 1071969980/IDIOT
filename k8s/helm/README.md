# IDIOT Platform Helm Chart

## 快速开始

```bash
# 部署到 k8s 集群
helm install idiot ./

# 部署测试环境（独立命名空间，不会与生产冲突）
helm install idiot-test ./ -f values-test.yaml

# 自定义项目路径（迁移到新机器时）
helm install idiot ./ --set projectRoot=/your/path/IDIOT

# 仅渲染不部署（检查输出）
helm template idiot ./

# 按文件渲染（调试单个模板）
helm template idiot ./ --show-only templates/06-neo4j.yaml

# 按文件渲染 + 测试环境配置
helm template idiot ./ -f values-test.yaml --show-only templates/06-neo4j.yaml

# 同时渲染多个文件
helm template idiot ./ --show-only templates/06-neo4j.yaml --show-only templates/07-weaviate.yaml
```

## 前置条件

- Kubernetes 集群（单节点 minikube/kind 即可）
- Helm 3
- 以下镜像需在集群节点上可用（已加载或可拉取）：
  - `idiot-api:latest` — 项目主服务，需本地构建
  - `idiot-git-server:v0.01` — Git 服务，需本地构建
  - `weaviateclusterapp:latest` — Weaviate 管理界面，需本地构建（仅 weaviateWebapp 启用时）

## 服务开关

部分服务默认不部署，可通过 `--set` 或 values 文件开启：

| 服务 | 默认状态 | 开启方式 |
|------|---------|---------|
| neo4j | 关闭 | `--set neo4j.enabled=true` |
| weaviate | 关闭 | `--set weaviate.enabled=true` |
| weaviate-webapp | 关闭 | `--set weaviateWebapp.enabled=true` |

默认部署的服务清单：

```
redis, postgres, juicefs-postgres, minio, juicefs-minio,
prometheus, otel-collector, git-server, api,
user-pod-scheduler, app-notification, nginx
```

## 主要配置项

部署时最常需要修改的值：

```bash
# 项目根目录（迁移到新机器时只需改这一项）
--set projectRoot=/home/gmh/桌面/IDIOT

# NodePort 端口
--set nodePorts.prometheus=30090
--set nodePorts.nginx=30143
```

所有配置项见 `values.yaml`。

## 测试环境

`values-test.yaml` 预配置了独立环境：

- 命名空间加 `test-` 前缀，与生产隔离
- 存储路径使用 `volumes/test/` 子目录
- NodePort 端口避开生产端口
- 所有服务默认开启

```bash
# 部署测试环境
helm install idiot-test ./ -f values-test.yaml

# 卸载测试环境
helm uninstall idiot-test
```

## 验证部署

```bash
# 检查所有 Pod 是否 Running
kubectl get pods -n idiot

# 检查服务暴露
kubectl get svc -n idiot

# 访问 API（通过 NodePort）
curl http://localhost:30143/api/

# 访问 Prometheus
curl http://localhost:30090/prometheus/
```

## 目录结构

```
k8s/helm/
  Chart.yaml              # Chart 元数据
  values.yaml             # 默认配置值
  values-test.yaml        # 测试环境配置覆层
  configs/                # 配置文件（自动嵌入 ConfigMap）
    nginx-default.conf
    proxy_cors.inc
    otel-collector-config.yml
    prometheus-config.yaml
  templates/
    _helpers.tpl          # 公共模板函数
    00-namespace.yaml     # 命名空间
    01-secrets.yaml       # 密钥
    02-configmap.yaml     # 应用配置
    03-storage.yaml       # 持久化存储 (PV/PVC)
    04-redis.yaml ~ 09.1-juicefs-minio.yaml   # 数据服务
    10-prometheus.yaml ~ 11-otel-collector.yaml # 监控服务
    12-git-server.yaml ~ 13.3-app-notification-task.yaml  # 应用服务
    14-nginx.yaml ~ 15-nodeports.yaml   # 网络层
```

## 迁移到新机器

将项目复制到新机器后，只需修改 `projectRoot`，所有相对路径自动拼接：

```yaml
# values.yaml — 仅需改这一项
projectRoot: "/新机器上的项目目录"

# 以下相对路径属于项目结构，通常不需要改
storage:
  relativePath: "k8s/volumes"
nginx:
  sslRelativePath: "nginx/ssl"
```

或通过命令行覆盖：

```bash
helm install idiot ./ --set projectRoot=/data/idiot
```
