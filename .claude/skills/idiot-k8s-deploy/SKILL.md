---
name: idiot-k8s-deploy
description: |
  在现有 Kubernetes 集群上部署额外的 IDIOT 平台实例（dev/test/staging 等环境）。
  涵盖从预检、配置决策、values 文件生成、部署执行到验证排错的全流程。
  当用户提到"部署新环境"、"再部署一套"、"部署 dev/test/staging 环境"、"新增 IDIOT 实例"、
  "k8s 部署"、"helm install"、"values 文件"等关键词时触发此技能。
---

# IDIOT K8s 多环境部署技能

## 概述

本技能指导在已有 IDIOT 平台的 k8s 集群上部署额外的环境实例。IDIOT 使用 Helm chart 管理，
通过 `namespacePrefix` 实现环境隔离，每个环境拥有独立的命名空间、StorageClass 和 NodePort。

Chart 路径：`k8s/helm/`

## 部署流程

### 第一步：集群预检

在实际操作前，全面采集集群现状。以下检查**全部并行执行**：

```bash
# 1. 现有命名空间
kubectl get ns | grep idiot

# 2. 现有 Helm release
helm list --all-namespaces

# 3. NodePort 占用（含其他服务）
kubectl get svc --all-namespaces -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
ports = []
for svc in data['items']:
    if svc['spec']['type'] == 'NodePort':
        ns = svc['metadata']['namespace']
        name = svc['metadata']['name']
        for p in svc['spec']['ports']:
            np = p.get('nodePort', 0)
            if np:
                ports.append((np, ns, name, p['port']))
for np, ns, name, tp in sorted(ports):
    print(f'  {np} -> {ns}/{name}:{tp}')
print(f'已占用 NodePort 数: {len(ports)}')
"

# 4. CPU 资源余量
kubectl describe node | grep -A5 'Allocated resources'

# 5. 现有 Helm release 的 values（用于获取 projectRoot 等配置）
helm get values <已有release名>
```

### 第二步：确认用户决策

基于预检结果，逐项与用户确认。使用 `AskUserQuestion` 工具，一次最多 4 个问题：

**必须确认的决策：**

1. **命名空间前缀** — 建议格式 `<env>-`（如 `dev-`、`test-`、`staging-`）
2. **Helm release 名称** — 建议与命名空间一致（如 `dev-idiot`）
3. **NodePort 端口方案** — 根据已占用端口推荐不冲突的范围，展示预览
4. **projectRoot** — 是否与现有环境共用路径（nginx SSL 证书依赖此项）
5. **StorageClass 名称** — 必须独立，不能复用已有 release 的 StorageClass
6. **密钥** — 沿用默认值还是生成独立密钥

**关键原则：**
- StorageClass 是集群级资源，Helm 通过 annotation 管理归属。两个 release 不能共用同名 StorageClass，否则 `helm install` 会因 ownership metadata 冲突而失败。每个环境必须使用独立的 StorageClass 名称（如 `dev-idiot-local`）。
- NodePort 是全局资源，端口不能重复。按环境分段管理（生产 302xx、测试 312xx、开发 303xx）。

### 第三步：生成 values overlay 文件

根据用户决策，在 `k8s/helm/` 下创建 `values-<env>.yaml`。

模板结构：

```yaml
# <env> 环境覆层
namespacePrefix: "<env>-"

projectRoot: "<与现有环境一致的路径>"

storage:
  className: "<env>-idiot-local"

nodePorts:
  postgres: <port>
  juicefsPostgres: <port>
  minio: <port>
  juicefsMinio: <port>
  nginx: <port>
```

参考已有的 `values-test.yaml` 作为示例。

### 第四步：干跑验证

生成配置后，先用 `helm template` 验证渲染结果，再实际部署：

```bash
cd k8s/helm
helm template <release名> ./ -f values-<env>.yaml 2>&1 | head -30
```

重点验证：
- 命名空间名称正确（`<prefix>idiot`、`<prefix>idiot-user-space`、`<prefix>idiot-user-space-storage`）
- NodePort 端口值正确
- StorageClass 名称正确且所有 PVC 都引用它

### 第五步：执行部署

```bash
helm install <release名> ./ -f values-<env>.yaml
```

### 第六步：验证与排错

部署后立即检查（并行执行）：

```bash
kubectl get pods -n <prefix>idiot -o wide
kubectl get pvc -n <prefix>idiot
kubectl get pvc -n <prefix>idiot-user-space-storage
kubectl get svc -n <prefix>idiot
kubectl get svc -n <prefix>idiot-user-space-storage
```

## 常见问题与处理

### StorageClass ownership 冲突

**现象：** `helm install` 报错 `StorageClass "xxx" exists and cannot be imported into the current release: invalid ownership metadata`

**原因：** StorageClass 是集群级资源，已被其他 Helm release 创建并拥有。

**解决：** 在 values overlay 中设置独立的 `storage.className`，如 `dev-idiot-local`。不要尝试复用。

### CPU 不足导致 Pod Pending

**现象：** Pod 状态为 `Pending`，事件显示 `Insufficient cpu`。

**排查：**
```bash
kubectl describe node | grep -A5 'Allocated resources'
```

**处理方案（按优先级）：**
1. 检查集群中其他服务的资源请求是否过高
2. 在新环境的 values 中降低非核心服务的 CPU 请求
3. 扩容集群节点

### otel-collector Init:CrashLoopBackOff

**现象：** otel-collector 的 init 容器 `check-langfuse-keys` 反复失败。

**原因：** `LANGFUSE_PUBLIC_KEY` 或 `LANGFUSE_SECRET_KEY` 为空，init 容器检查不通过。

**解决：** 配置正确的 Langfuse OTel key：
```bash
kubectl patch secret idiot-secrets -n <prefix>idiot -p '{"stringData":{"LANGFUSE_PUBLIC_KEY":"<key>","LANGFUSE_SECRET_KEY":"<key>"}}'
```
然后删除 Pod 让其重建。注意：修改 Secret 后已运行的 Pod 不会自动更新环境变量，需要重建 Pod。

### git-server CrashLoopBackOff

**现象：** git-server 反复崩溃重启。

**原因：** 启动脚本末尾推送仓库内容时报 `fatal: not a git repository`。这是已知 bug，生产环境也存在。

**影响：** git 仓库初始化部分已完成，此错误不影响核心功能。

**处理：** 记录为已知问题，不做特殊处理。

## 卸载环境

```bash
helm uninstall <release名>
```

PVC 数据根据 StorageClass 的 `reclaimPolicy` 决定是否保留。默认 `Delete` 会自动清理。
