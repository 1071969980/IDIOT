# CLAUDE.md

本文件为在此代码库中工作时提供指导。

## 指令遵循
1. Only Try to complete the selcected TODO at a time.


## 项目概述

IDIOT (Intelligent Development Integrated & Operations Toolkit) 是一个基于 Python 的 AI 应用程序构建工具包。项目采用微服务架构，专注于基于图的工作流执行、负载均衡和全面的可观测性。

## 开发环境
   
### Python 环境
- **Python 版本**: 需要 3.13+
- **包管理器**: uv (Astral UV)
- **环境设置**: 
  ```bash
  uv python install 3.13
  uv sync
  ```

### 开发命令
- **运行测试**: `pytest testcase/`
- **构建 Docker 镜像**: `docker build ./ -f ./api/Dockerfile -t idiot-api:latest`
- **使用 Docker Compose 运行**: `cd docker && docker compose -p idiot up -d`
- **调试模式**: 设置 `API_DEBUG=1` 环境变量以启用 VS Code 调试

## 架构概述

### 核心组件

1. **图执行器** (`api/graph_executor/`)
   - 基于 DAG 的工作流执行系统，使用装饰器和类型注解定义节点
   - 支持节点间连接、拉取依赖和执行顺序的自动拓扑排序
   - 提供节点跳过机制和断点续执行功能
   - 关键文件: `graph.py`, `graph_core.py`
   - 详细文档: `docs/source/Components/Graph Executor.rst`

2. **负载均衡器** (`api/load_balance/`)
   - 智能路由决策的微服务架构组件
   - 支持多种负载均衡策略（轮询、随机等）
   - 内置自动重试机制和错误处理
   - 提供服务注册中心和配置管理
   - 关键文件: `load_balancer.py`, `service_regeistry.py`
   - 详细文档: `docs/source/Components/Load Blancer.rst`

3. **LLM 集成** (`api/llm/`)
   - 多个 LLM 提供商的统一接口
   - 内置重试和错误处理
   - 流式支持
   - 关键文件: `generator.py`, `deepseek.py`, `tongyi.py`

4. **向量数据库** (`api/vector_db/`)
   - 向量存储的抽象层
   - 包含 Weaviate 实现
   - 支持相似性搜索和知识管理

5. **人机协作** (`api/human_in_loop/`)
   - 基于 WebSocket 的实时人工干预系统
   - 使用 Redis 消息流确保消息可靠传递
   - 支持 JSON-RPC 2.0 协议的双向通信
   - 提供中断请求和通知功能
   - 关键文件: `interrupt.py`, `notification.py`, `ws_worker/`
   - 详细文档: `docs/source/Components/Human In The Loop.rst`

6. **日志系统** (`api/logger/`)
   - 基于 OpenTelemetry 的可观测性解决方案
   - 集成 Jaeger 分布式追踪和 Prometheus 指标收集
   - 提供 `log_span` 装饰器简化追踪跨度创建
   - 支持同步和异步函数的自动包装
   - 关键文件: `logger.py`
   - 详细文档: `docs/source/Components/Logger System.rst`

### 应用结构

主 FastAPI 应用程序 (`api/app/main.py`) 包含以下路由器：
- 文档处理 (`document/`)
- 文本分块 (`chunk/`)
- 合同审查 (`contract_review/`)
- 收据识别 (`receipt_recognize/`)
- 向量数据库操作 (`vector_db/`)

### 工作流示例

合同审查工作流展示了架构：
```python
# 基于 LLM 集成的图工作流
@Graph("contract_review")
@dataclass
class ContractReviewWorkflow:
    contract_content: str
    
    async def run(self) -> "ReviewResult":
        # 使用负载均衡器调用 LLM 服务
        # 为关键决策实现人机协作
        # 将结果存储在向量数据库中以供将来参考
        pass
```

## 关键设计模式

### 基于图的执行
- 工作流定义为有向无环图 (DAG)，使用 `@Graph` 和 `@dataclass` 装饰器
- 节点通过返回值类型注解定义连接，通过参数声明拉取依赖
- 支持节点跳过机制和断点续执行功能
- 自动拓扑排序确定执行顺序，支持并行执行

### 负载均衡策略
- 服务注册中心管理多个服务实例和配置
- 支持轮询、随机等多种负载均衡策略
- 内置指数退避重试机制和错误处理
- 策略模式设计，易于扩展新的均衡算法

### 人机协作模式
- 基于 WebSocket 的实时双向通信
- 使用 Redis 消息流确保消息可靠传递
- 支持 JSON-RPC 2.0 协议和消息确认机制
- 提供中断请求和通知功能，支持工作流人工干预

### 可观测性
- 基于 OpenTelemetry 的完整可观测性解决方案
- 集成 Jaeger 分布式追踪和 Prometheus 指标收集
- 提供 `log_span` 装饰器简化追踪创建
- 支持跨异步操作的生命周期感知日志记录

## 开发指南

### 代码组织
- 遵循 `api/` 中已建立的模块结构
- 使用 Pydantic 模型进行数据验证
- 为 I/O 操作实现 async/await 模式
- 使用 `@Graph("workflow_name")` 和 `@dataclass` 装饰工作流节点
- 利用 `log_span` 装饰器添加追踪跨度
- 通过 `interrupt()` 和 `notification()` 函数实现人机交互

### 错误处理
- 使用各模块的自定义异常和错误类型
- 为外部服务调用实现重试逻辑和指数退避
- 使用 Logfire 记录带有适当上下文的错误
- 通过负载均衡器优雅地处理速率限制和服务不可用
- 人机协作模块提供超时和取消机制

### 测试
- 将测试文件放在 `testcase/` 目录中
- 使用 pytest 进行单元测试
- 在测试中模拟外部服务
- 测试成功和失败场景
- 使用 OpenTelemetry 测试工具验证追踪数据
- 测试人机协作的消息流处理

### 配置管理
- 使用环境变量存储敏感数据
- 将配置存储在适当的模块常量中
- 使用 `python-dotenv` 进行本地开发
- 生产部署使用 Docker secrets
- 负载均衡器服务配置通过 `ServiceConfig` 管理
- 日志系统端点通过 `LOGFIRE_LOG_ENDPOINT` 配置

## 部署

### 容器设置
- 多服务 Docker Compose 配置
- Nginx 反向代理与 SSL 终止
- PostgreSQL 用于持久数据存储
- Redis 用于缓存和会话管理
- Weaviate 用于向量数据库操作
- SeaweedFS 用于对象存储

### 监控堆栈
- Jaeger 用于分布式追踪，可视化请求流转过程
- Prometheus 用于指标收集和告警
- OpenTelemetry 收集器用于遥测数据的中央处理
- Logfire 用于应用程序生命周期日志记录和跨度创建

### 生产注意事项
- 所有服务都在 Nginx 反向代理后运行
- 持久数据存储在命名卷中
- 为所有服务实现健康检查
- 实现优雅关闭处理
- WebSocket 连接需要 JWT token 认证
- Redis 消息流有自动过期机制
- OpenTelemetry 数据流需要适当的网络配置

## 常见开发任务

### 添加新的 LLM 提供商
1. 在 `api/load_balance/` 中创建服务实例类，继承 `ServiceInstanceBase`
2. 实现 AsyncOpenAI 接口或相应的委托函数
3. 在 `LOAD_BLANCER` 中注册服务并配置重试策略
4. 添加配置到 docker-compose.yml
5. 参考文档: `docs/source/Components/Load Blancer.rst`

### 创建新工作流
1. 使用 `@Graph("workflow_name")` 和 `@dataclass` 装饰器定义工作流类
2. 实现 `async def run(self)` 方法，通过返回值类型注解定义节点连接
3. 通过参数声明拉取依赖，使用 `ParamsList` 和 `ParamsLineageDict` 处理多来源数据
4. 使用负载均衡器进行外部服务调用
5. 添加 `log_span` 装饰器进行追踪
6. 参考文档: `docs/source/Components/Graph Executor.rst`

### 实现人机协作功能
1. 在工作流中使用 `HILMessageStreamContext` 管理会话
2. 调用 `interrupt()` 函数等待用户输入
3. 使用 `notification()` 函数发送通知
4. 实现 WebSocket 客户端处理 JSON-RPC 2.0 协议
5. 参考文档: `docs/source/Components/Human In The Loop.rst` 和示例 `examples/human_in_loop_client.py`

### 添加新的存储后端
1. 实现向量数据库接口
2. 添加连接管理和错误处理
3. 更新配置和依赖项
4. 编写全面的测试

### SQL 与 PostgreSQL 交互范式

本项目采用基于文件的 SQL 模板系统与 PostgreSQL 进行交互，避免了 ORM 的复杂性，保持了 SQL 的原生能力。

**核心特点**：
- SQL 语句按功能块组织在 `.sql` 文件中，使用 `--` 注释作为分隔符
- 使用 `parse_sql_file()` 自动解析 SQL 文件为 Python 变量
- 基于 `@dataclass` 的数据模型和异步数据库操作
- 统一的错误处理模式和参数化查询
- 触发器和其他数据库对象集成到表创建流程中

#### parse_sql_file() 机制

`parse_sql_file()` 函数解析 SQL 文件的规则：
- 以 `--` 开头的行被视为注释块
- 注释块的最后一行作为 SQL 语句的键名（去除 `--` 前缀）
- 注释块后的非空行作为 SQL 语句内容
- 重复键名会被覆盖，后出现的有效

示例格式：
```sql
-- This is a comment block
-- The last line becomes the key
SELECT * FROM users WHERE id = :id;

-- Single comment line
INSERT INTO users (name) VALUES (:name);
```

#### 文件夹结构

```
api/[module]/sql_stat/[table_name]/
├── TableName.sql    # SQL 语句定义
└── utils.py         # 数据访问层和模型
```

#### 最简代码示例

**SQL 文件** (`UserTable.sql`):
```sql
-- CreateUser
INSERT INTO users (uuid, username) VALUES (:uuid, :username);

-- QueryUser
SELECT * FROM users WHERE uuid = :uuid_value;
```

**utils.py**:
```python
from api.sql_orm_models.utils import parse_sql_file
from pathlib import Path

sql_statements = parse_sql_file(Path(__file__).parent / "UserTable.sql")
CREATE_USER = sql_statements["CreateUser"]
QUERY_USER = sql_statements["QueryUser"]

@dataclass
class _UserCreate:
    username: str
    uuid: Optional[str] = None

async def create_user(user_data: _UserCreate) -> str:
    if not user_data.uuid:
        user_data.uuid = str(uuid4())

    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_USER), {
            "uuid": user_data.uuid,
            "username": user_data.username
        })
        await conn.commit()
        return user_data.uuid
```

#### 关系说明

1. **SQL 文件**：定义所有数据库操作的 SQL 语句模板
2. **utils.py**：
   - 解析 SQL 文件为常量
   - 定义数据模型（`@dataclass`）
   - 实现异步数据库操作函数
3. **外部使用**：通过导入 utils.py 中的函数进行数据库操作

#### 数据库初始化时机

在导入相关模块时，会出发数据库初始化逻辑。

#### UUID 设计规则

**具体规则**：

1. **数据库层面**：
   - 使用 `id UUID PRIMARY KEY DEFAULT uuidv7()` 让数据库自动生成UUID，不再提供其他UUID字段
   - INSERT语句使用 `RETURNING id` 子句立即返回生成的UUID
   - 不在INSERT语句中手动传入UUID参数

2. **Python层面**：
   - **不主动生成UUID**：移除所有 `uuid4()` 调用

3. **数据模型**：
   - Python数据模型中UUID字段使用 `UUID` 类型
   - 创建操作的数据模型不应包含UUID字段

**正确示例**：

```sql
-- 正确的INSERT语句
INSERT INTO users (name, email)
VALUES (:name, :email)
RETURNING id;
```

```python
# 正确的Python处理
async def create_user(data: UserCreate) -> UUID:
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_USER),
            {"name": data.name, "email": data.email}
        )
        await conn.commit()

        return result.scalar()
```

**错误示例**：
```python
# 错误：Python生成UUID
user_id = uuid4()
await conn.execute(text(INSERT), {"id": user_id, ...})
```

### 配置日志和追踪
1. 设置 `LOGFIRE_LOG_ENDPOINT` 环境变量
2. 使用 `@log_span` 装饰器标记关键函数
3. 配置 OpenTelemetry Collector 处理数据流
4. 通过 Jaeger UI 查看追踪数据
5. 参考文档: `docs/source/Components/Logger System.rst`

## 环境变量

开发必需：
- `DASHSCOPE_API_KEY`: Qwen/Tongyi API 访问
- `DEEPSEEK_API_KEY`: DeepSeek 模型访问
- `JWT_SECRET_KEY`: 认证密钥
- `LOGFIRE_LOG_ENDPOINT`: OpenTelemetry 端点（通常设置为 `http://otel_collector:4318`）

可选：
- `API_DEBUG`: 启用调试模式 (0/1)
- `API_DEBUG_PORT`: 调试端口（默认：5678）
- `CACHE_DIR`: 缓存目录路径

## 文档结构

详细的技术文档位于 `docs/` 目录：

- `docs/source/Components/` - 各组件详细文档
- `docs/source/User Guide/` - 用户指南和部署说明
- `examples/` - 示例代码和客户端实现
- `docs/source/index.rst` - 文档入口点

使用 Sphinx 构建文档：
```bash
cd docs
make html
```
