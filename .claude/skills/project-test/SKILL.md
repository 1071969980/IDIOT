---
name: project-test
description: IDIOT 项目自动化测试技能。当用户提到测试、验证、构建镜像、运行测试、冒烟测试、集成测试等关键词时触发此技能。覆盖从代码变更分析到镜像构建、服务启动、功能验证的完整测试流程。即使用户只提到"测试一下"或"跑一下测试"，也应触发此技能。
---

# IDIOT 项目自动化测试

项目部署在 Kubernetes 上，包含两个自定义镜像。测试流程按阶段推进，每个阶段依赖前一个阶段的结果。

## 测试阶段总览

```
1. 变更分析 → 判断需要测试什么
2. 镜像构建 → 构建受影响的镜像
3. 服务部署 → K8s 滚动更新重启受影响的 Deployment
4. 调试器连接 → attach 到 debugpy 阻塞的服务，解除阻塞并监听异常
5. 功能验证 → 运行 API 测试、集成测试、异常触发测试
6. 结果汇总 → 输出测试报告
```

当前已完成的阶段文档：

| 阶段 | 参考文档 | 状态 |
|------|---------|------|
| 变更分析 + 镜像构建 | [references/docker-build.md](references/docker-build.md) | 可用 |
| 服务部署 | [references/service-deploy.md](references/service-deploy.md) | 可用 |
| 调试器连接 | [references/debug-attach.md](references/debug-attach.md) | 可用 |
| 功能验证 | 认证模块: [references/api-auth.md](references/api-auth.md) | 可用 |
| 用户资源维护 | [references/user-resource-cleanup.md](references/user-resource-cleanup.md) | 可用 |
| 功能验证 | 会话模块: [references/api-chat-session.md](references/api-chat-session.md) | 可用 |
| 功能验证 | 其他模块: 待补充 | - |

## 功能验证文档编写原则

功能验证阶段的参考文档不是测试脚本集合，而是**面向 AI 编写测试脚本的知识库**。每个模块的参考文档应包含：

1. **渐进式披露** — SKILL.md 只列模块索引，详细概念和代码片段在 references/ 中按模块拆分
2. **概念优先** — 详细介绍项目关键概念和基本使用方法（认证机制、路由结构、服务访问方式等），让 AI 理解"为什么这样测试"
3. **原子代码片段** — 不提供完整测试脚本，而是提供独立的、可复用的代码片段（如"登录获取会话"、"令牌健康检查"），作为 AI 编写复杂测试脚本的构建块
4. **三方一致性** — 每个模块文档开头要求确认 skill 描述、API 文档（`docs/api/`）、源代码三者一致，避免过时信息。优先引用已有的 API 文档和项目代码，而非在 skill 中重复定义行为

## 测试行为约束

### 逐步确认

每个测试步骤执行前应向用户说明意图并征求确认。除非用户明确表示可以全自动完成测试，否则不要连续推进多个步骤。

### 关键环境信息

测试开始时需确认以下信息（提供默认值，用户可覆盖）：

| 信息 | 默认值 | 用途 |
|------|--------|------|
| K8s 命名空间（主服务） | `idiot` | api、nginx、user-pod-scheduler 等 Deployment |
| K8s 命名空间（用户空间） | `idiot-user-space` | 用户 Pod、PVC、Secret 等 |
| K8s 命名空间（存储） | `idiot-user-space-storage` | JuiceFS PostgreSQL、MinIO |
| 测试用户名 | `user_test` | 注册/登录测试 |
| 测试用户密码 | `password_test` | 注册/登录测试 |

### 文档一致性守卫

测试过程中若发现项目的实际行为或实现与 SKILL 及其参考文档中的描述不一致，**立即中断当前测试步骤**，向用户报告差异，确认实际情况后判断是否需要更新文档。保持文档与项目实际一致后再继续测试。

## 测试环境要求

- Docker 已运行
- Python 3.13+ 环境（`uv run` 可用）
- kubectl 可访问目标集群（服务部署阶段必需）
- agent-debugger CLI 已安装（调试器连接阶段必需）
