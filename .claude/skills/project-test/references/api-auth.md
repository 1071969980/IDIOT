# 认证模块测试

用户认证是所有 API 测试的前置条件。本文介绍认证流程的核心概念，并提供基于 Python 会话的测试代码片段。

## 前置检查

测试前，确认以下三方内容一致：

1. **SKILL 文档**（本文件）中的端点路径、参数、响应格式
2. **API 文档** `docs/api/auth.apib`
3. **源代码** `api/app/auth/token.py`

若发现不一致，以源代码为准，更新文档。

## 关键概念

### 认证流程

```
注册 (signup) → 登录 (token) → 携带凭证访问受保护端点 → 登出 (logout)
                                            ↕
                                      刷新令牌 (refresh_token)
```

所有受保护的 API 端点都要求有效的认证凭证。测试脚本通常遵循"注册 → 登录 → 测试 → 清理"的模式。

### JWT Cookie 机制

服务端使用 JWT (HS256) 作为认证令牌。令牌不直接返回给客户端管理，而是通过 `Set-Cookie` 响应头写入 `auth_token` cookie：

| 属性 | 值 | 说明 |
|------|-----|------|
| Name | `auth_token` | 固定名称 |
| HttpOnly | `true` | JavaScript 不可读取 |
| Secure | `true` | 仅 HTTPS 传输 |
| SameSite | `lax` | CSRF 防护 |
| Path | `/` | 全站可用 |

令牌负载仅包含 `sub`（用户 UUID）和 `exp`（过期时间戳），不包含角色或权限信息。

### 登录模式

通过 `rememberMe` 查询参数控制令牌有效期：

| 模式 | rememberMe | 有效期 | Cookie Max-Age |
|------|-----------|--------|----------------|
| 普通登录 | `false`（默认） | 15 分钟 | 900 秒 |
| 记住我 | `true` | 服务端配置（默认 30 天） | 对应天数 |

### Python 会话（推荐）

`requests.Session` 自动管理 cookie 生命周期——登录后服务端设置 `auth_token` cookie，Session 会在后续请求中自动携带。无需手动提取和注入令牌。

```python
import requests

session = requests.Session()
```

Session 同时支持设置 `base_url`（Python 3.11+ 的 requests 库），避免重复拼接 URL：

```python
session = requests.Session()
session.base_url = "https://localhost:8143/api"  # 通过 nginx 访问
```

若 requests 版本不支持 `base_url`，可直接拼接字符串。

### 路由结构

FastAPI 应用设置了 `root_path="/api"`，auth 路由前缀为 `/auth`。完整路径：

```
/api/auth/token           # 登录
/api/auth/signup          # 注册
/api/auth/user_exists     # 检查用户名
/api/auth/token_healthy   # 令牌健康检查
/api/auth/refresh_token   # 刷新令牌
/api/auth/logout          # 登出
/api/auth/user/{user_id}  # 删除用户
```

### 服务访问

在 K8s 测试环境中，通过 port-forward 访问服务：

```bash
# 通过 nginx（生产路径）
kubectl port-forward -n idiot svc/nginx 8143:8143 &
# → base_url = "http://localhost:8143/api"（注意：K8s nginx 为 HTTP，非 HTTPS）
```

通过 nginx 访问无需 SSL 证书验证。

## K8s 测试环境下的 Secure Cookie 问题

`auth_token` cookie 设置了 `Secure=True`，浏览器和 `requests` 库不会在 HTTP 连接上发送 Secure cookie。但 K8s nginx 的 8143 端口是 HTTP（没有 SSL 终止），所以 `requests.Session` 的自动 cookie 管理会失效。

**原因**：生产环境中，前端 nginx（如 TideWave）在 443 端口做 SSL 终止（自签名证书），客户端到 nginx 是 HTTPS，Secure cookie 正常发送。K8s 内部 nginx 不做 SSL 终止。

**解决方式**：登录后手动提取 token，通过 `Cookie` header 传递：

```python
resp = session.post(f"{BASE_URL}/auth/token", data={"username": "t", "password": "t"})
token = resp.cookies.get("auth_token")
session.headers.update({"Cookie": f"auth_token={token}"})
```

这等效于浏览器在 HTTPS 环境下的行为——后续所有请求都会携带 `auth_token`。

## 代码片段

以下片段均为基于 `requests.Session` 的原子操作，可自由组合。

### 创建测试会话

```python
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

session = requests.Session()
session.verify = False
BASE_URL = "http://localhost:8143/api"
```

### 用户注册

```python
resp = session.post(f"{BASE_URL}/auth/signup", json={
    "username": "test_user",
    "password": "test_password",
})
assert resp.status_code == 201
```

### 用户登录

登录后需手动设置 Cookie header（见上方 Secure Cookie 问题说明）。

```python
resp = session.post(
    f"{BASE_URL}/auth/token",
    data={"username": "test_user", "password": "test_password"},
)
assert resp.status_code == 200
body = resp.json()
assert body["token_type"] == "bearer"
assert "expires_in" in body

# 手动设置 Cookie header（K8s HTTP 环境必须）
token = resp.cookies.get("auth_token")
session.headers.update({"Cookie": f"auth_token={token}"})
```

**注意**：登录请求使用 `application/x-www-form-urlencoded`（`data=` 参数），不是 JSON。

### 令牌健康检查

验证当前会话的认证状态。

```python
resp = session.post(f"{BASE_URL}/auth/token_healthy")
assert resp.status_code == 204  # 令牌有效
```

### 登出

```python
resp = session.post(f"{BASE_URL}/auth/logout")
assert resp.status_code == 200
assert resp.json()["message"] == "登出成功"
# session 中的 auth_token 已失效
```

### 清理：删除用户

只能删除当前登录用户自身。需要先登录获取有效会话。

```python
# 假设已知 user_id（从 token 解码或其他途径获取）
resp = session.delete(f"{BASE_URL}/auth/user/{user_id}")
assert resp.status_code == 200
```

### 完整的会话生命周期示例

```python
# 注册 → 登录 → 设置cookie → 验证 → 清理
session.post(f"{BASE_URL}/auth/signup", json={"username": "t", "password": "t"})
r = session.post(f"{BASE_URL}/auth/token", data={"username": "t", "password": "t"})
session.headers.update({"Cookie": f"auth_token={r.cookies.get('auth_token')}"})
assert session.post(f"{BASE_URL}/auth/token_healthy").status_code == 204
session.post(f"{BASE_URL}/auth/logout")
```

此模式可作为每个测试用例的 setup/teardown 模板。
