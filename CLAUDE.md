# CLAUDE.md

本文件为在此代码库中工作时提供指导。

## 项目概述

IDIOT (Intelligent Development Integrated & Operations Toolkit) 是一个基于 Python 的 AI 应用程序后端工具包。

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
   - 开发指南: `docs/for_LLM_dev/添加新的LLM提供商.md`

5. **人机协作** (`api/human_in_loop/`)
   - 基于协程的程序中断请求人工干预系统
   - 使用 Redis 消息流确保消息可靠传递
   - 详细文档: `docs/source/Components/Human In The Loop.rst`

6. **日志系统** (`api/logger/`)
   - 基于 OpenTelemetry 的可观测性解决方案
   - 集成 langfuse 分布式追踪和 Prometheus 指标收集
   - 提供 `log_span` 装饰器简化追踪跨度创建
   - 支持同步和异步函数的自动包装
   - 关键文件: `logger.py`
   - 详细文档: `docs/source/Components/Logger System.rst`

## 部署

### 容器设置
- 多服务 Docker Compose 配置
- Nginx 反向代理与 SSL 终止
- PostgreSQL 用于持久数据存储
- Redis 用于缓存和会话管理
- Weaviate 用于向量数据库操作
- SeaweedFS 用于对象存储

### 监控堆栈
- langfuse 用于分布式追踪，可视化请求流转过程
- Prometheus 用于指标收集和告警
- OpenTelemetry 收集器用于遥测数据的中央处理
- Logfire 用于应用程序生命周期日志记录和跨度创建

## 常见开发任务

查阅 `docs/for_LLM_dev` 目录以了解本项目中的常见开发任务。

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

使用 Sphinx 构建文档：
```bash
cd docs
make html
```
