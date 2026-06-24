# api/rbac — IDIOT_RBAC 鉴权服务交互包

本包封装与独立部署的 **IDIOT_RBAC**（基于 casbin-rs 的分片鉴权服务）的交互，
提供 HTTP 客户端、业务原子语义工具函数、数据模型与异常。

服务地址（`base_url`）与鉴权 token 由统一配置模块
[`api/core/env_config.py`](../core/env_config.py) 的 `RBACConfig` 提供，
**不在本包内硬编码**。

---

## 一、RBAC 模型概念（必读）

IDIOT_RBAC 基于 casbin，但有一个关键设计选择：**角色按 `owner` 域绑定**。
理解这一点，其余就顺了。

### 1.1 维度

- 请求维度：`r = sub, owner, project, obj, act`
- 策略维度：`p = sub_role, owner, project_pattern, obj_pattern, act, eft`
- 角色分组：`g = (user, role, owner)`

其中：

| 维度 | 含义 |
|---|---|
| `sub` / `user` | 操作者（当前用户标识） |
| `owner` | **资源所有者**（租户/工作区，多租户隔离轴） |
| `project` | owner 内的项目名 |
| `obj` | 被访问对象（支持 `keyMatch`，如 `/api/*`） |
| `act` | 操作（`read` / `write` / `*`） |
| `eft` | 策略效果：`allow` / `deny` |

> ⚠️ `owner` 是“资源归属”，`sub` 是“操作者”——鉴权时 `owner` 来自被访问资源，
> `sub` 来自当前用户。**别混淆。**

### 1.2 策略效果

**deny-overrides**：`some(allow) && !some(deny)`——任一 `deny` 命中即拒绝。
即先用 `allow` 给大范围放行，再用 `deny` 收回特例。

### 1.3 匹配器（核心）

```
m = (p.sub_role == ""  ||  g(r.sub, p.sub_role, r.owner))   # 公开 或 用户在该 owner 域内持有该角色
  && keyMatch(r.owner,    p.owner)
  && keyMatch(r.project,  p.project_pattern)
  && keyMatch(r.obj,      p.obj_pattern)
  && keyMatch(r.act,      p.act)
```

⚠️ 最易踩的点：角色检查 `g(r.sub, p.sub_role, r.owner)` 用的是**请求里的 `r.owner`**
（资源所有者），不是策略里的 `p.owner`。也就是说——**“你是谁的角色”是相对于
“这个资源归谁”来判定的**。这就是多租户隔离的来源。

### 1.4 四个核心设计支柱

| 支柱 | 怎么表达 | 含义 |
|---|---|---|
| **owner 域 = 租户/工作区** | `g, bob, editor, alice` | bob 仅在 alice 的资源域里是 editor；对别人资源无此角色 |
| **公开策略** | `sub_role = ""`（空） | 无需任何角色，所有人可命中（匿名/公开分享） |
| **全局策略** | `owner = "*"` | 广播到所有分表，对任意 owner 生效（但仍要过该 owner 域的角色检查） |
| **deny-overrides + keyMatch** | `eft=deny`；`/api/*`、`*` | 定向收回权限；一条策略覆盖一批资源 |

> 关键：**全局策略 ≠ 全员放行**。`owner=*` 的策略仍要过 `g(sub, role, r.owner)`，
> 所以全局 `p, admin, *, *, *, *, allow` 不会让 A 租户的 admin 管 B 租户。

---

## 二、推荐角色体系（面向多租户平台）

| 角色 | 定位 | 典型策略 |
|---|---|---|
| `admin` | 资源所有者/租户管理员，对自己的域全权 | `p, admin, *, *, *, *, allow`（全局，但角色按域绑定） |
| `editor` | 可读写协作 | `p, editor, <owner>, *, /docs/*, write, allow` |
| `viewer` | 只读协作 | `p, viewer, <owner>, *, *, read, allow` |
| `member` | 普通成员（可创建、读） | 项目内受限写 |
| `(public)` | 匿名（空 `sub_role`） | `p, , <owner>, *, /public/*, read, allow` |

本包常量 [`ADMIN_ROLE`](constants.py)（`"admin"`）对应默认全局 admin 策略；
[`PUBLIC_ROLE`](constants.py)（`""`）用于公开策略。

---

## 三、典型策略配方

**1. 自有资源全权**（alice 访问自己的资源，`r.owner = alice`）
```
g, alice, admin, alice                 # alice 在 alice 域里是 admin
p, admin, *, *, *, *, allow            # 全局：admin 对其所在域全权
```
判 `enforce(alice, alice, *, /x, write)` → `g(alice, admin, alice)` ✓ → allow。

**2. 协作授权**（让 bob 能编辑 alice 的文档）
```
g, bob, editor, alice
p, editor, alice, *, /docs/*, write, allow
```

**3. 公开分享**（任何人可读 alice 的公开区）
```
p, , alice, *, /public/*, read, allow    # 空 sub_role = 公开
```

**4. 定向拒绝**（朋友能看 bob 的 `/api/*`，但 `backend` 项目除外）
```
p, friend, *, *, /api/*, *, allow
p, friend, bob, backend, *, *, deny      # deny 覆盖 allow
g, alice, friend, bob
```

**5. 项目级隔离**（把敏感项目锁死）
```
p, admin, acme, secret, *, *, deny       # 连 admin 在 acme 的 secret 项目也被拒
```

---

## 四、包结构与公共 API

| 文件 | 关键导出 |
|---|---|
| [`client.py`](client.py) | [`RBACClient`](client.py)、[`get_rbac_client()`](client.py) |
| [`util.py`](util.py) | 业务原子语义函数（见下） |
| [`data_model.py`](data_model.py) | `PolicyEntry`、`RoleAssignmentEntry`、`EnforceResponse`、`StatusResponse`、`PolicyEffect` |
| [`constants.py`](constants.py) | 路径/头/效果/通配符常量 |
| [`exceptions.py`](exceptions.py) | `RBACError` 及子类 |

`RBACClient`（[`client.py`](client.py)）原子方法签名：

```python
class RBACClient:
    def __init__(self, base_url=None, token=None, timeout=DEFAULT_TIMEOUT_SECONDS): ...
    async def health(self) -> bool
    async def ready(self) -> bool
    async def enforce(self, sub, owner, project, obj, act, *, explain=False) -> EnforceResponse
    async def create_policy(self, entry: PolicyEntry) -> StatusResponse
    async def list_policies(self, owner=None) -> list[PolicyEntry]
    async def delete_policy(self, entry: PolicyEntry) -> StatusResponse
    async def assign_role(self, user, role, owner) -> StatusResponse
    async def list_role_assignments(self, owner=None) -> list[RoleAssignmentEntry]
    async def remove_role_assignment(self, user, role, owner) -> StatusResponse
    async def close(self) -> None
```

业务原子语义（[`util.py`](util.py)，每个函数均可传 `client=`，缺省用 `get_rbac_client()`）：

```python
async def enforce_access(sub, owner, project, obj, act, *, client=None) -> bool
async def require_access(sub, owner, project, obj, act, *, client=None) -> None  # deny 抛 RBACPermissionDenied
async def is_admin(sub, owner, *, client=None) -> bool
async def grant_role(user, role, owner, *, client=None) -> None
async def revoke_role(user, role, owner, *, client=None) -> None
async def list_user_roles(user, owner, *, client=None) -> list[str]
async def set_public_access(obj_pattern, *, act="read", eft=EFFECT_ALLOW, owner=GLOBAL_OWNER, project_pattern=PROJECT_ANY, client=None) -> None
async def bootstrap_owner(owner, admin_user, *, admin_role=ADMIN_ROLE, client=None) -> None
```

---

## 五、使用示例（引用具体代码）

下面把第三节的概念配方，落到本包的具体调用上。

### 5.0 获取客户端

```python
from api.rbac import get_rbac_client          # api/rbac/client.py —— 懒加载全局单例
client = get_rbac_client()
```

> 单例的 `base_url` / `token` 来自 [`api/core/env_config.py`](../core/env_config.py)
> 的 `rbac_config.rbac_service_base_url` 与 `rbac_config.rbac_service_token`。
> 应用关闭时应调用 `await get_rbac_client().close()`（建议接入 FastAPI lifespan shutdown）。

### 5.1 自有资源全权（新租户初始化）

直接用 [`bootstrap_owner`](util.py)（内部调用 `assign_role`，默认角色
[`ADMIN_ROLE`](constants.py)）：

```python
from api.rbac import bootstrap_owner
await bootstrap_owner(owner="alice", admin_user="alice")   # → assign_role("alice","admin","alice")
```

等价于原始调用：

```python
from api.rbac import RBACClient
await RBACClient().assign_role("alice", "admin", "alice")
# 配合默认全局策略  p, admin, *, *, *, *, allow  即获得对自有资源的全权
```

### 5.2 协作授权（让 bob 编辑 alice 的文档）

```python
from api.rbac import grant_role                      # api/rbac/util.py
from api.rbac import PolicyEntry                     # api/rbac/data_model.py
from api.rbac import get_rbac_client

client = get_rbac_client()
await grant_role("bob", "editor", "alice", client=client)            # g, bob, editor, alice
await client.create_policy(PolicyEntry(                              # p, editor, alice, *, /docs/*, write, allow
    sub_role="editor", owner="alice", project_pattern="*",
    obj_pattern="/docs/*", act="write", eft="allow",
))
```

### 5.3 公开分享（任何人可读公开区）

用 [`set_public_access`](util.py)（自动填入空 `sub_role` =
[`PUBLIC_ROLE`](constants.py)、owner = [`GLOBAL_OWNER`](constants.py)）：

```python
from api.rbac import set_public_access
await set_public_access("/public/*", owner="alice")   # p, , alice, *, /public/*, read, allow
```

### 5.4 鉴权判定（业务侧放行门）

放行门（布尔）与守卫（拒绝即抛异常）：

```python
from api.rbac import enforce_access, require_access
from api.rbac import RBACPermissionDenied            # api/rbac/exceptions.py

# 布尔判定
if await enforce_access("bob", "alice", "backend", "/docs/1", "read"):
    ...

# 守卫子句：deny 时抛 RBACPermissionDenied
try:
    await require_access("bob", "alice", "backend", "/docs/1", "write")
except RBACPermissionDenied:
    ...  # 返回 403
```

需要命中策略详情时直接用底层 `enforce`：

```python
resp = await get_rbac_client().enforce("bob", "alice", "backend", "/docs/1", "write", explain=True)
print(resp.allow, resp.explain)   # explain 为命中的 [sub_role,owner,project_pattern,obj_pattern,act,eft]
```

### 5.5 定向拒绝（开洞收回权限）

```python
from api.rbac import PolicyEntry
from api.rbac.constants import EFFECT_DENY           # api/rbac/constants.py

await get_rbac_client().create_policy(PolicyEntry(
    sub_role="editor", owner="alice", project_pattern="secret",
    obj_pattern="*", act="*", eft=EFFECT_DENY,        # 即便 editor 也无法访问 alice 的 secret 项目
))
```

### 5.6 查询与清理

```python
client = get_rbac_client()
policies   = await client.list_policies(owner="alice")          # 返回该 owner 策略 + 全局策略
assignments = await client.list_role_assignments(owner="alice") # 角色分配

from api.rbac import list_user_roles
roles = await list_user_roles("bob", "alice")                  # bob 在 alice 域内的角色

# 回收协作权限
from api.rbac import revoke_role
await revoke_role("bob", "editor", "alice", client=client)

# 删除策略（按完整匹配）
await client.delete_policy(PolicyEntry(
    sub_role="editor", owner="alice", project_pattern="*",
    obj_pattern="/docs/*", act="write", eft="allow",
))
```

---

## 六、配置（env_config）

[`api/core/env_config.py`](../core/env_config.py) 的 `RBACConfig`：

| 字段 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `k8s_service_rbac_name` | `K8S_SERVICE_RBAC_NAME` | `idiot-rbac` | RBAC 服务名 |
| `k8s_namespace_rbac` | `K8S_NAMESPACE_RBAC` | `idiot_rbac` | RBAC 所在命名空间 |
| `rbac_service_port` | `RBAC_SERVICE_PORT` | `8080` | 端口 |
| `rbac_service_token_value` | `RBAC_SERVICE_TOKEN` | — | Bearer Token（**必填，未设则鉴权 401**） |

- `rbac_config.rbac_service_base_url`（计算属性）= `http://{name}.{ns}.{cluster_domain}:{port}`，
  默认 `http://idiot-rbac.idiot_rbac.svc.cluster.local:8080`。
- `rbac_config.rbac_service_token`（惰性 property）：未设时访问才抛 `ValueError`
  （符合 main 分支“不在 import 时访问必填环境变量”的惰性原则）。

部署前提：部署 IDIOT_RBAC 时建议设 `fullnameOverride: idiot-rbac` 使默认服务名生效；
不同 release 则覆盖 `K8S_SERVICE_RBAC_NAME`。`RBAC_SERVICE_TOKEN` 必须与 RBAC chart
的 token 一致。

---

## 七、异常与错误处理

[`exceptions.py`](exceptions.py) 定义统一异常层次，客户端按 HTTP 状态映射：

| HTTP / 情况 | 异常 |
|---|---|
| 网络/超时/连接重试耗尽 | `RBACConnectionError` |
| 400 bad_request | `RBACBadRequestError` |
| 401 unauthorized | `RBACUnauthorizedError` |
| 403 forbidden（如删文件级全局策略） | `RBACForbiddenError` |
| 5xx internal_error | `RBACServerError` |
| 其它非 2xx | `RBACError`（基类） |
| 业务侧 `require_access` 命中 deny | `RBACPermissionDenied` |

所有异常均继承 `RBACError`，可统一捕获。连接级错误（`ConnectError`/`ConnectTimeout`）
会按 [`DEFAULT_CONNECT_RETRIES`](constants.py)（=2）重试——IDIOT_RBAC 为 headless
StatefulSet，重试大概率命中其它健康 Pod。

---

## 八、设计要点与陷阱

1. **owner 是“资源归属”，sub 是“操作者”**——别混淆。
2. **角色天然按 owner 隔离**——无需为“租户 A 的 editor 不能动租户 B”额外写策略。
3. **全局策略仍要过 owner 域角色检查**——`p, admin, *, ...` 不会让 A 的 admin 管 B。
4. **deny 用来“开洞”**——先 allow 大范围，再 deny 特例；别用 allow 枚举。
5. **keyMatch 通配要克制**——规划好 `obj_pattern` 命名空间，避免误匹配过宽。
6. **文件级全局策略受保护**——由 ConfigMap `policy.csv` 定义的（如默认 admin）**不可
   经 API 删除**（返回 403），运行时只能加 owner 级策略。
