---
文档标题：system_notification_spec_context
文档描述：系统公告功能的开发上下文，包含项目代码基础设施、SQL模式、Redis模式、FastAPI应用结构等关键技术信息。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

## 目录

- [1. 项目SQL数据库交互模式](#1-项目sql数据库交互模式)
  - [1.1 SQL模板系统](#11-sql模板系统)
  - [1.2 数据库连接与连接池](#12-数据库连接与连接池)
  - [1.3 数据模型与UUID规则](#13-数据模型与uuid规则)
  - [1.4 批量操作与IN子句](#14-批量操作与in子句)
- [2. Redis使用模式](#2-redis使用模式)
  - [2.1 连接配置](#21-连接配置)
  - [2.2 Stream操作](#22-stream操作)
  - [2.3 分布式锁](#23-分布式锁)
  - [2.4 发布订阅](#24-发布订阅)
- [3. FastAPI应用结构](#3-fastapi应用结构)
  - [3.1 主应用入口](#31-主应用入口)
  - [3.2 模块化路由组织](#32-模块化路由组织)
  - [3.3 认证依赖](#33-认证依赖)
- [4. K8s部署模式](#4-k8s部署模式)
  - [4.1 Kustomize管理](#41-kustomize管理)
  - [4.2 API部署配置](#42-api部署配置)
  - [4.3 启动脚本](#43-启动脚本)
  - [4.4 ConfigMap与Secret](#44-configmap与secret)
- [5. 独立FastAPI应用的创建](#5-独立fastapi应用的创建)
  - [5.1 应用入口文件](#51-应用入口文件)
  - [5.2 独立启动脚本](#52-独立启动脚本)
  - [5.3 独立K8s部署配置](#53-独立k8s部署配置)

---

## 1. 项目SQL数据库交互模式

项目采用基于文件的SQL模板系统与PostgreSQL交互，避免ORM复杂性，保持SQL原生能力。完整参考：[SQL模板与数据库交互](../../for_LLM_dev/SQL模板与数据库交互.md)。

### 1.1 SQL模板系统

`parse_sql_file()` 函数解析 `.sql` 文件，规则如下：
- 以 `--` 开头的行被视为注释块
- 注释块的最后一行作为SQL语句的键名（去除 `--` 前缀）
- 注释块后的非空行作为SQL语句内容
- 使用 `--\n`（单独的 `--` 行加换行）作为分隔符时，多条SQL语句被解析为 `list[str]`

文件结构：
```
api/[module]/sql_stat/[table_name]/
├── TableName.sql      # SQL语句定义
├── utils.py           # 数据访问层和模型
└── __init__.py        # 可选的包初始化文件
```

`utils.py` 中的典型解析模式：

```python
from pathlib import Path
from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "TableName.sql"
sql_statements = parse_sql_file(sql_file_path)

INSERT_ENTITY = sql_statements["InsertEntity"]
CREATE_TABLE = sql_statements["CreateTable"]  # list[str] 类型
```

### 1.2 数据库连接与连接池

连接配置位于 `api/sql_utils/constant.py`：

```python
ASYNC_SQL_ENGINE = create_async_engine(async_sql_url, **_ENGINE_KWARGS)
```

连接池通用配置（`_ENGINE_KWARGS`）：
- `pool_size`: 5
- `max_overflow`: 10
- `pool_pre_ping`: True（使用前检查连接有效性）
- `pool_recycle`: 1800（每30分钟回收连接）
- `future`: True

数据库URL格式：`postgresql+asyncpg://postgres:{password}@postgres:5432/postgres`

### 1.3 数据模型与UUID规则

数据模型使用 `@dataclass`，命名以下划线开头（如 `_EntityCreate`），表示不应被其他模块直接存储或长期持有。

**UUID规则**：
- 数据库层面：`id UUID PRIMARY KEY DEFAULT uuidv7()`，由数据库自动生成
- INSERT语句使用 `RETURNING id` 获取生成的UUID
- Python层面不主动生成UUID，不在INSERT语句中手动传入UUID参数
- 创建操作的数据模型不包含UUID字段

典型插入操作：

```python
async def insert_entity(entity_data: _EntityCreate) -> UUID:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(INSERT_ENTITY), { ... })
        await conn.commit()
        return result.scalar()  # RETURNING id
```

### 1.4 批量操作与IN子句

**批量插入**使用 `unnest()` 函数，需要 SQLAlchemy 类型注解：

```python
from sqlalchemy.dialects.postgresql import ARRAY, UUID as SQLTYPE_UUID
from sqlalchemy import bindparam

result = await conn.execute(
    text(INSERT_BATCH).bindparams(
        bindparam("ids_list", type_=ARRAY(SQLTYPE_UUID)),
    ),
    {"ids_list": entity_ids}
)
```

**IN子句**使用 `expanding=True`：

```python
result = await conn.execute(
    text(DELETE_BY_IDS).bindparams(
        bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID),
    ),
    {"ids_list": entity_ids}
)
```

**注意**：`ARRAY` 类型用于 `unnest()` 的批量插入，`expanding=True` 用于 `IN (...)` 的批量查询/删除。

## 2. Redis使用模式

### 2.1 连接配置

定义于 `api/redis/constants.py`：

```python
from redis.asyncio import Redis
CLIENT = Redis(host="redis", port=6379, protocol=3)
```

### 2.2 Stream操作

通用Stream写入函数位于 `api/redis/__init__.py`：

```python
async def xadd_msg_with_expired(
    stream_key: str, msg: bytes, msg_id: str, expired_time: int
) -> None:
    await CLIENT.xadd(stream_key, {"msg": msg, "msg_id": msg_id})
    await CLIENT.expire(stream_key, expired_time)
```

Human-in-the-Loop场景有专用版本 `HIL_xadd_msg_with_expired`，位于 `api/redis/human_in_loop.py`，使用 `HIL_RedisMsg` Pydantic模型。

### 2.3 分布式锁

`RedisDistributedLock` 上下文管理器位于 `api/redis/distributed_lock.py`，支持：
- SET NX EX 原子操作
- 自动续期（看门狗机制）
- Lua脚本安全释放
- 防止多锁的 `MultiLockError`

使用方式：

```python
# 上下文管理器
async with RedisDistributedLock("my_lock", timeout=30) as lock:
    pass

# 装饰器
@distributed_lock("my_lock")
async def my_function():
    pass

# 动态key
@distributed_lock(lambda bound: f"user_lock:{bound.arguments['user_id']}")
async def my_function(user_id: str):
    pass
```

### 2.4 发布订阅

位于 `api/redis/pubsub.py`：

- `publish_event(channel)` - 向指定频道发布事件
- `subscribe_to_event(channel, event)` - 订阅频道并设置 `asyncio.Event`

`subscribe_to_event` 应作为后台任务运行，收到消息后自动取消订阅。

**注意**：本项目目前没有现成的 Redis+PostgreSQL 双写模式，系统公告功能需要新建此模式。

## 3. FastAPI应用结构

详细参考：[声明新的FastAPI接口](../../for_LLM_dev/声明新的FastAPI接口.md)。

### 3.1 主应用入口

主应用入口位于 `api/app/main.py`，关键模式：

- 使用 `asynccontextmanager` 管理 `lifespan`（启动时初始化数据库、连接池，关闭时优雅停止后台任务）
- 使用 `@distributed_lock("init_postgres_db")` 装饰器保护数据库初始化，防止多实例并发初始化
- 调试模式通过 `api/core/env_config.py` 的 `debug_config.api_debug` 控制，支持 `debugpy` 远程调试
- CORS中间件、验证异常处理器等在主应用中配置
- 路由注册通过 `app.include_router(xxx_router)` 集中管理
- `root_path="/api"` 用于反向代理路径前缀

数据库初始化遵循显式调用原则：各模块提供 `create_table()` 函数，在 `init_db()` 中集中调用，不自动执行。

### 3.2 模块化路由组织

每个功能模块遵循三文件结构：

| 文件 | 职责 |
|------|------|
| `router_declare.py` | 定义 `APIRouter` 实例，配置 `prefix` 和 `tags` |
| `data_model.py` | 定义请求/响应的 Pydantic 模型 |
| `endpoints.py` | 实现具体的接口逻辑 |

`router_declare.py` 示例（参考 `api/app/auth/router_declare.py`）：

```python
from fastapi import APIRouter

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)
```

### 3.3 认证依赖

位于 `api/authentication/utils.py`，提供两个主要依赖：

- `get_current_active_user` -> `_User`：获取完整用户对象，已删除用户会抛出400异常
- `get_current_user_id` -> `str`：仅获取用户ID字符串，适用于不需要完整用户信息的场景

两者均支持 Cookie（`remember_me` token）和 Bearer Token 双重认证方式。

## 4. K8s部署模式

### 4.1 Kustomize管理

`k8s/base/kustomization.yaml` 按序声明所有资源文件，当前包含15个资源（从 `00-namespace.yaml` 到 `15-host-services.yaml`）。新增服务需在此文件中添加对应的资源引用。

### 4.2 API部署配置

`k8s/base/12-api.yaml` 包含：
- **ServiceAccount**: `api`（命名空间 `idiot`）
- **RBAC**: `api-user-pod-access` Role/RoleBinding（跨命名空间 `idiot-user-space` 的Pod访问权限）
- **Deployment**: 单副本，使用 `idiot-api:latest` 镜像，启动命令 `./api/run.sh`
- **Service**: 暴露端口 8000（http）和 5678（debug）
- **资源限制**: 请求 512Mi/200m，上限 2Gi/1000m

环境变量通过 `configMapRef`（`idiot-config`）和 `secretRef`（`idiot-secrets`）注入。

### 4.3 启动脚本

`api/run.sh` 的模式：

```bash
source .venv/bin/activate
if [ "$API_DEBUG" != "0" ]; then
    uvicorn api.app.main:app --host 0.0.0.0 --port 8000
else
    gunicorn api.app.main:app \
        --workers 4 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --log-level debug \
        --forwarded-allow-ips='*' \
        --preload
fi
```

调试模式使用 uvicorn 单进程，生产模式使用 gunicorn 4 worker + uvicorn worker。

### 4.4 ConfigMap与Secret

- ConfigMap: `k8s/base/02-configmap.yaml`，存放非敏感配置项
- Secret: `k8s/base/01-secrets.yaml`，存放密码、密钥等敏感信息

两者均通过 `envFrom` 方式注入到容器环境变量中，应用层通过 `api/core/env_config.py` 读取。

## 5. 独立FastAPI应用的创建

系统公告功能需要创建独立的FastAPI应用进程，与主API应用解耦。

### 5.1 应用入口文件

创建 `api/app/system_notification_app.py`，参考主应用 `api/app/main.py` 的模式：

- 使用 `asynccontextmanager` 管理 `lifespan`
- 在 `lifespan` 启动阶段初始化公告功能相关的数据库表
- 独立的 `root_path` 配置（如 `/system-notification`）
- 只注册系统公告相关的路由模块
- 使用 `@distributed_lock("init_notification_db")` 装饰器保护数据库初始化，防止多实例并发建表。**注意**：这是对主应用 `@distributed_lock("init_postgres_db")` 模式的借鉴与改进——主应用使用了该装饰器，而 User Pod Scheduler 应用（`api/app/user_pod_scheduler_app.py`）未使用。对于新创建的公告应用，推荐使用分布式锁以在多 worker 场景下提供更好的保护。
- 可选复用认证依赖（从 `api/authentication` 导入）

### 5.2 独立启动脚本

创建 `api/system_notification_app.sh`，参考 `api/run.sh` 模式：

```bash
source .venv/bin/activate
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

注意使用不同的端口号（如 8001），避免与主API冲突。Worker数量可根据业务负载调整。

### 5.3 独立K8s部署配置

创建 `k8s/base/12.2-system-notification-api.yaml`（编号接在 `12.1-user-pod-scheduler.yaml` 之后），包含：

- **Deployment**: 使用相同的 `idiot-api:latest` 镜像（同一代码库），启动命令改为 `./api/system_notification_app.sh`
- **Service**: 暴露独立端口
- **资源限制**: 可低于主API，如请求 256Mi/100m，上限 1Gi/500m
- 同样通过 `configMapRef` 和 `secretRef` 注入环境变量

创建后在 `k8s/base/kustomization.yaml` 中添加资源引用：

```yaml
- 12.2-system-notification-api.yaml
```
