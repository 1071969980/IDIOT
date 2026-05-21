# 用户资源手动维护

测试过程中可能产生残留数据（API 调用失败、进程中断、级联删除未触发等），需要直接操作 K8s 和数据库进行清理。

清理顺序与 `delete_user` 端点一致：**K8s 资源 → JuiceFS → 数据库记录**。

## 前置概念

### 用户资源层级

每个用户注册后可能产生以下资源（按创建顺序）：

| 层级 | 资源 | 命名规则 | 位置 |
|------|------|---------|------|
| DB | `simple_users` 记录 | UUID 主键 | 主 PostgreSQL |
| DB | `user_pod_records` 记录 | FK → simple_users (CASCADE) | 主 PostgreSQL |
| K8s | Secret | `juicefs-secret-user-{user_id}` | `idiot-user-space` |
| K8s | StorageClass | `juicefs-storage-class-user-{user_id}` | 集群级 |
| K8s | PVC | `juicefs-pvc-user-{user_id}` | `idiot-user-space` |
| K8s | PV | 动态创建 | 集群级 |
| K8s | Pod | `user-space-pod-user-{user_id}` | `idiot-user-space` |
| JuiceFS | PostgreSQL 数据库 | `juicefs-user-{user_id}` | juicefs-postgres |
| JuiceFS | MinIO bucket | `juicefs-user-{user_id}` | MinIO |

资源按需创建：注册只创建 DB 记录，首次访问文件系统才创建 K8s + JuiceFS 资源。

### 命名规则来源

所有 K8s 资源命名由 `api/juiceFS/string_utils.py` 的 `get_string_var()` 统一生成。手动操作时直接使用 `user-{user_id}` 后缀即可匹配。

### 删除顺序（重要）

参照 `api/user_pod_scheduler/k8s_resources.py` 的 `delete_user_k8s_resources()`：

```
1. Pod       → 释放 PVC，CSI Node 自动清理 Mount Pod
2. 记录 PV 名 → PVC 删除后 PV 名不可查
3. PVC       → 删除后 PV 变 Released（Retain 策略，数据保留）
4. PV        → 手动删除 Released PV（仅 K8s 元数据）
5. StorageClass
6. Secret
```

## 代码片段

### 查询用户列表

```bash
# 查询所有用户（主数据库 pod 内）
kubectl exec -n idiot $(kubectl get pods -n idiot -l app=postgres -o name | head -1) \
  -- psql -U postgres -d postgres -c \
  'SELECT id, user_name, create_time FROM simple_users ORDER BY create_time DESC;'
```

### 检查用户的 K8s 资源

一次性查看某用户的所有 K8s 资源（含 PV）：

```bash
UID="<user_id>"
echo "=== Pod / PVC / Secret ==="
kubectl get pod,pvc,secret -n idiot-user-space -o name 2>/dev/null | grep "$UID"
echo "=== PV ==="
kubectl get pv -o name 2>/dev/null | grep "$UID"
echo "=== StorageClass ==="
kubectl get storageclass -o name 2>/dev/null | grep "$UID"
```

### 清理用户的 K8s 资源

按正确顺序删除，`--ignore-not-found` 跳过不存在的资源：

```bash
UID="<user_id>"
NS="idiot-user-space"

# 1. 删除 Pod
kubectl delete pod "user-space-pod-user-$UID" -n "$NS" --ignore-not-found

# 2. 获取 PV 名（PVC 删除前）
PV=$(kubectl get pvc "juicefs-pvc-user-$UID" -n "$NS" -o jsonpath='{.spec.volumeName}' 2>/dev/null)

# 3. 删除 PVC
kubectl delete pvc "juicefs-pvc-user-$UID" -n "$NS" --ignore-not-found
kubectl wait pvc "juicefs-pvc-user-$UID" -n "$NS" --for=delete --timeout=60s 2>/dev/null

# 4. 删除 PV（Retain 策略需手动）
[ -n "$PV" ] && kubectl delete pv "$PV" --ignore-not-found

# 5. 删除 StorageClass + Secret
kubectl delete storageclass "juicefs-storage-class-user-$UID" --ignore-not-found
kubectl delete secret "juicefs-secret-user-$UID" -n "$NS" --ignore-not-found
```

### 批量清理多个用户

```bash
# 设置要清理的 user_id 列表
UIDS=(
  "019e2add-3e26-73b9-af4d-2ba55110ac61"
  "019e2a65-13a5-7599-82d5-649bf91197fe"
)

# 批量检查
for uid in "${UIDS[@]}"; do
  echo "=== $uid ==="
  kubectl get pod,pvc,secret -n idiot-user-space -o name 2>/dev/null | grep "$uid"
  kubectl get pv -o name 2>/dev/null | grep "$uid"
  kubectl get storageclass -o name 2>/dev/null | grep "$uid"
done

# 批量清理（复用上面的删除逻辑）
for uid in "${UIDS[@]}"; do
  echo "--- Cleaning $uid ---"
  kubectl delete pod "user-space-pod-user-$uid" -n idiot-user-space --ignore-not-found
  PV=$(kubectl get pvc "juicefs-pvc-user-$uid" -n idiot-user-space -o jsonpath='{.spec.volumeName}' 2>/dev/null)
  kubectl delete pvc "juicefs-pvc-user-$uid" -n idiot-user-space --ignore-not-found
  [ -n "$PV" ] && kubectl delete pv "$PV" --ignore-not-found
  kubectl delete storageclass "juicefs-storage-class-user-$uid" --ignore-not-found
  kubectl delete secret "juicefs-secret-user-$uid" -n idiot-user-space --ignore-not-found
done
```

### 清理数据库记录

K8s 资源清理完毕后，删除数据库记录：

```bash
PG_POD=$(kubectl get pods -n idiot -l app=postgres -o name | head -1)

# 删除用户（CASCADE 自动清理 user_pod_records 等关联表）
kubectl exec -n idiot $PG_POD -- psql -U postgres -d postgres -c \
  "DELETE FROM simple_users WHERE id = '<user_id>';"

# 批量删除
kubectl exec -n idiot $PG_POD -- psql -U postgres -d postgres -c \
  "DELETE FROM simple_users WHERE user_name LIKE 'test_%';"
```

### 清理 JuiceFS 资源

JuiceFS 资源位于独立的 PostgreSQL 和 MinIO（都在 `idiot-user-space-storage` 命名空间），参照 `api/juiceFS/creator.py` 的 `delete_juicefs_for_user()`。

删除顺序：先 PostgreSQL 数据库（终止连接 + DROP），再 MinIO bucket（递归删除对象 + 删除 bucket）。

```bash
# 单用户 JuiceFS 清理
JUICEFS_PG=$(kubectl get pods -n idiot-user-space-storage -l app=juicefs-postgres -o jsonpath='{.items[0].metadata.name}')
MINIO_POD=$(kubectl get pods -n idiot-user-space-storage -l app=juicefs-minio -o jsonpath='{.items[0].metadata.name}')
MINIO_USER=$(kubectl exec -n idiot-user-space-storage $MINIO_POD -- printenv MINIO_ROOT_USER)
MINIO_PASS=$(kubectl exec -n idiot-user-space-storage $MINIO_POD -- printenv MINIO_ROOT_PASSWORD)
UID="<user_id>"

# 1. 终止连接 + 删除 PostgreSQL 数据库
kubectl exec -n idiot-user-space-storage $JUICEFS_PG -- psql -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'juicefs-user-$UID' AND pid <> pg_backend_pid();"
kubectl exec -n idiot-user-space-storage $JUICEFS_PG -- psql -U postgres -c \
  "DROP DATABASE IF EXISTS \"juicefs-user-$UID\";"

# 2. 递归删除 MinIO bucket
kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc alias set local http://localhost:9000 "$MINIO_USER" "$MINIO_PASS"
kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc rm --recursive --force "local/juicefs-user-$UID"
kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc rb "local/juicefs-user-$UID"
```

### 批量清理 JuiceFS

```bash
UIDS=("uid1" "uid2")
JUICEFS_PG=$(kubectl get pods -n idiot-user-space-storage -l app=juicefs-postgres -o jsonpath='{.items[0].metadata.name}')
MINIO_POD=$(kubectl get pods -n idiot-user-space-storage -l app=juicefs-minio -o jsonpath='{.items[0].metadata.name}')
MINIO_USER=$(kubectl exec -n idiot-user-space-storage $MINIO_POD -- printenv MINIO_ROOT_USER)
MINIO_PASS=$(kubectl exec -n idiot-user-space-storage $MINIO_POD -- printenv MINIO_ROOT_PASSWORD)

for uid in "${UIDS[@]}"; do
  DB="juicefs-user-$uid"
  echo "--- JuiceFS: $uid ---"
  kubectl exec -n idiot-user-space-storage $JUICEFS_PG -- psql -U postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND pid <> pg_backend_pid();"
  kubectl exec -n idiot-user-space-storage $JUICEFS_PG -- psql -U postgres -c \
    "DROP DATABASE IF EXISTS \"$DB\";"
  kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc rm --recursive --force "local/$DB"
  kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc rb "local/$DB"
done
```

### 检查残留资源

一次性检查所有层面的残留：

```bash
# JuiceFS 数据库
JUICEFS_PG=$(kubectl get pods -n idiot-user-space-storage -l app=juicefs-postgres -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n idiot-user-space-storage $JUICEFS_PG -- psql -U postgres -c '\l' | grep juicefs-user

# MinIO buckets
MINIO_POD=$(kubectl get pods -n idiot-user-space-storage -l app=juicefs-minio -o jsonpath='{.items[0].metadata.name}')
MINIO_USER=$(kubectl exec -n idiot-user-space-storage $MINIO_POD -- printenv MINIO_ROOT_USER)
MINIO_PASS=$(kubectl exec -n idiot-user-space-storage $MINIO_POD -- printenv MINIO_ROOT_PASSWORD)
kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc alias set local http://localhost:9000 "$MINIO_USER" "$MINIO_PASS" 2>/dev/null
kubectl exec -n idiot-user-space-storage $MINIO_POD -- mc ls local/

# K8s 资源
kubectl get pod,pvc,secret -n idiot-user-space -o name | grep user-
kubectl get pv -o name | grep juicefs-pv-user
kubectl get storageclass -o name | grep juicefs-storage-class-user

# 用户记录
PG_POD=$(kubectl get pods -n idiot -l app=postgres -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n idiot $PG_POD -- psql -U postgres -d postgres -c \
  'SELECT id, user_name, create_time FROM simple_users ORDER BY create_time DESC;'
```

## 完整清理流程

```
1. 查询用户 → psql SELECT
2. 清理 K8s 资源 → kubectl delete（Pod → PVC → PV → StorageClass → Secret）
3. 清理 JuiceFS → DROP DATABASE + mc rm/rb
4. 删除用户记录 → psql DELETE（CASCADE 清理关联表）
```
