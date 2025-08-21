# CLAUDE.md

本文件为在此代码库中工作时提供指导。

## 指令遵循
1. It is important to pay attention to user notes that begin with three asterisks '***'! stop you work and rethink solution.
2. Only Try to complete one selcection TODO at a time.
3. Be very careful about users' refusal to modify your files.


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

### 附加依赖
- **spaCy 模型**: 从 `pip_resources/` 下载并安装中文语言模型
  ```bash
  cd ./pip_resources
  ./download_spacy_model.sh
  source ./.venv/bin/activate
  uv pip install *.whl
  ```

### 开发命令
- **运行测试**: `pytest testcase/`
- **构建 Docker 镜像**: `docker build ./ -f ./api/Dockerfile -t idiot-api:latest`
- **使用 Docker Compose 运行**: `cd docker && docker compose -p idiot up -d`
- **调试模式**: 设置 `API_DEBUG=1` 环境变量以启用 VS Code 调试

## 架构概述

### 核心组件

1. **图执行器** (`api/graph_executor/`)
   - 基于 DAG 的工作流执行系统
   - 使用装饰器和类型注解定义节点
   - 支持同步和异步执行
   - 关键文件: `graph.py`, `graph_core.py`

2. **负载均衡器** (`api/load_balance/`)
   - 防止调用 ML 模型服务时的速率限制
   - 可插拔策略模式（默认轮询）
   - 指数退避重试逻辑
   - 关键文件: `load_balancer.py`, `service_regeistry.py`

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
   - 基于 WebSocket 的实时人工干预
   - 工作流中断的通知系统
   - 人工决策的上下文管理

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
class ContractReviewWorkflow:
    async def review_contract(self, contract_content: str) -> ReviewResult:
        # 使用负载均衡器调用 LLM 服务
        # 为关键决策实现人机协作
        # 将结果存储在向量数据库中以供将来参考
```

## 关键设计模式

### 基于图的执行
- 工作流定义为有向无环图 (DAG)
- 节点是具有类型注解方法的装饰类
- 节点间自动参数传递
- 支持并行执行和条件分支

### 负载均衡策略
- 服务注册时包含配置（最大重试次数、超时等）
- 策略实现实例选择逻辑
- 内置断路器模式以实现容错

### 可观测性
- 使用 Logfire 和 OpenTelemetry 进行全面日志记录
- 使用 Jaeger 进行分布式追踪
- 使用 Prometheus 进行指标收集
- 生命周期感知的日志记录，跨越异步操作

## 开发指南

### 代码组织
- 遵循 `api/` 中已建立的模块结构
- 使用 Pydantic 模型进行数据验证
- 为 I/O 操作实现 async/await 模式
- 使用 `@Graph("workflow_name")` 装饰工作流节点

### 错误处理
- 使用各模块的自定义异常
- 为外部服务调用实现重试逻辑
- 使用 Logfire 记录带有适当上下文的错误
- 通过负载均衡器优雅地处理速率限制

### 测试
- 将测试文件放在 `testcase/` 目录中
- 使用 pytest 进行单元测试
- 在测试中模拟外部服务
- 测试成功和失败场景

### 配置管理
- 使用环境变量存储敏感数据
- 将配置存储在适当的模块常量中
- 使用 `python-dotenv` 进行本地开发
- 生产部署使用 Docker secrets

## 部署

### 容器设置
- 多服务 Docker Compose 配置
- Nginx 反向代理与 SSL 终止
- PostgreSQL 用于持久数据存储
- Redis 用于缓存和会话管理
- Weaviate 用于向量数据库操作
- SeaweedFS 用于对象存储

### 监控堆栈
- Jaeger 用于分布式追踪
- Prometheus 用于指标收集
- OpenTelemetry 收集器用于遥测数据
- Logfire 用于应用程序生命周期日志记录

### 生产注意事项
- 所有服务都在 Nginx 反向代理后运行
- 持久数据存储在命名卷中
- 为所有服务实现健康检查
- 实现优雅关闭处理

## 常见开发任务

### 添加新的 LLM 提供商
1. 在 `api/load_balance/` 中创建服务实例类
2. 实现 AsyncOpenAI 接口
3. 在 `LOAD_BLANCER` 中注册服务
4. 添加配置到 docker-compose.yml

### 创建新工作流
1. 使用 `@Graph` 装饰器定义工作流类
2. 实现具有适当类型注解的节点方法
3. 使用负载均衡器进行外部服务调用
4. 添加适当的日志记录和错误处理

### 添加新的存储后端
1. 实现向量数据库接口
2. 添加连接管理和错误处理
3. 更新配置和依赖项
4. 编写全面的测试

## 环境变量

开发必需：
- `DASHSCOPE_API_KEY`: Qwen/Tongyi API 访问
- `DEEPSEEK_API_KEY`: DeepSeek 模型访问
- `JWT_SECRET_KEY`: 认证密钥
- `LOGFIRE_LOG_ENDPOINT`: OpenTelemetry 端点

可选：
- `API_DEBUG`: 启用调试模式 (0/1)
- `API_DEBUG_PORT`: 调试端口（默认：5678）
- `CACHE_DIR`: 缓存目录路径
