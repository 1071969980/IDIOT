---
文档标题：mcp_client_spec_todo
文档描述：MCP Client 模块开发的待办事项列表。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接路径引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。
---

**目录**:
- [开发阶段 1: 配置模型](#开发阶段-1-配置模型)
- [开发阶段 2: 连接管理](#开发阶段-2-连接管理)
- [开发阶段 3: 工具映射](#开发阶段-3-工具映射)
- [开发阶段 4: 主适配器](#开发阶段-4-主适配器)
- [开发阶段 5: 测试与文档](#开发阶段-5-测试与文档)
- [开发后任务](#开发后任务)

---

## 开发阶段 1: 配置模型

### 任务 1.1: 创建目录结构

- [ ] 创建 `api/agent/tools/mcp/` 目录
- [ ] 创建子目录（如需要）

### 任务 1.2: 实现 `config_data_model.py`

- [ ] 实现 `McpServerConfig` 类
  - [ ] 定义 `url` 字段（必需）
  - [ ] 定义 `name` 字段（默认 "default"）
  - [ ] 定义 `timeout` 字段（默认 30.0）

- [ ] 实现 `McpToolFilter` 类
  - [ ] 定义 `allow_list` 字段（默认 None）
  - [ ] 定义 `deny_list` 字段（默认空列表）

- [ ] 实现 `McpClientConfig` 类
  - [ ] 定义 `enabled` 字段
  - [ ] 定义 `servers` 字段
  - [ ] 定义 `tool_filter` 字段
  - [ ] 定义 `include_server_name_in_tool_name` 字段
  - [ ] 定义 `json_response` 字段
  - [ ] 添加 `validate_servers` 验证器

### 任务 1.3: 配置模型测试

- [ ] 编写配置模型单元测试
  - [ ] 测试默认值
  - [ ] 测试验证逻辑
  - [ ] 测试序列化/反序列化

---

## 开发阶段 2: 连接管理

### 任务 2.1: 实现 `client.py` - `McpServerConnection`

- [ ] 实现 `__init__` 方法
  - [ ] 初始化连接参数
  - [ ] 初始化运行时状态字段

- [ ] 实现 `__aenter__` 方法
  - [ ] 创建 `streamable_http_client` 连接
  - [ ] 创建 `ClientSession`
  - [ ] 调用 `initialize()`
  - [ ] 添加错误处理和日志

- [ ] 实现 `__aexit__` 方法
  - [ ] 关闭 `ClientSession`
  - [ ] 关闭 `streamable_http_client`
  - [ ] 添加错误处理

- [ ] 实现 `list_tools` 方法
  - [ ] 调用 `session.list_tools()`
  - [ ] 返回工具列表

- [ ] 实现 `call_tool` 方法
  - [ ] 调用 `session.call_tool()`
  - [ ] 添加错误处理

### 任务 2.2: 实现 `client.py` - `McpClientManager`

- [ ] 实现 `__init__` 方法
  - [ ] 初始化配置
  - [ ] 初始化连接列表

- [ ] 实现 `__aenter__` 方法
  - [ ] 为每个 Server 创建 `McpServerConnection`
  - [ ] 进入每个连接的上下文

- [ ] 实现 `__aexit__` 方法
  - [ ] 退出所有连接的上下文

- [ ] 实现 `get_all_tools` 方法
  - [ ] 从所有连接获取工具
  - [ ] 返回 `{tool_name: (tool, connection)}` 字典

### 任务 2.3: 连接管理测试

- [ ] 编写 `McpServerConnection` 单元测试
  - [ ] 测试连接建立
  - [ ] 测试连接关闭
  - [ ] 测试工具列表获取

- [ ] 编写 `McpClientManager` 单元测试
  - [ ] 测试多 Server 连接
  - [ ] 测试所有连接的关闭
  - [ ] 测试工具聚合

---

## 开发阶段 3: 工具映射

### 任务 3.1: 实现 `tool_mapper.py` - 过滤函数

- [ ] 实现 `should_include_tool` 函数
  - [ ] 检查黑名单
  - [ ] 检查白名单
  - [ ] 返回过滤结果

### 任务 3.2: 实现 `tool_mapper.py` - `McpToolWrapper`

- [ ] 实现 `__init__` 方法
  - [ ] 存储 MCP 工具信息
  - [ ] 存储连接引用
  - [ ] 存储工具名称前缀

- [ ] 实现 `get_tool_param` 方法
  - [ ] 生成完整的工具名称
  - [ ] 创建 `ChatCompletionToolParam`
  - [ ] 调用 `_convert_input_schema`

- [ ] 实现 `_convert_input_schema` 方法
  - [ ] 转换 MCP inputSchema
  - [ ] 移除 OpenAI 不支持的字段

- [ ] 实现 `__call__` 方法
  - [ ] 调用 `connection.call_tool()`
  - [ ] 调用 `_convert_result`
  - [ ] 添加异常处理

- [ ] 实现 `_convert_result` 方法
  - [ ] 提取文本内容
  - [ ] 处理二进制数据
  - [ ] 检查错误标志
  - [ ] 返回 `ToolTaskResult`

### 任务 3.3: 工具映射测试

- [ ] 编写 `should_include_tool` 单元测试
  - [ ] 测试白名单过滤
  - [ ] 测试黑名单过滤
  - [ ] 测试混合过滤

- [ ] 编写 `McpToolWrapper` 单元测试
  - [ ] 测试工具参数生成
  - [ ] 测试 schema 转换
  - [ ] 测试工具调用
  - [ ] 测试结果转换

---

## 开发阶段 4: 主适配器

### 任务 4.1: 实现 `adapter.py` - `McpToolsLoader`

- [ ] 实现 `__init__` 方法
  - [ ] 存储配置
  - [ ] 初始化状态字段

- [ ] 实现 `__aenter__` 方法
  - [ ] 创建 `McpClientManager`
  - [ ] 进入管理器上下文
  - [ ] 获取所有工具
  - [ ] 应用过滤
  - [ ] 创建 `McpToolWrapper` 实例
  - [ ] 构建工具列表

- [ ] 实现 `__aexit__` 方法
  - [ ] 关闭管理器

- [ ] 实现 `tool_params` 属性
  - [ ] 返回工具参数列表
  - [ ] 检查是否已加载

- [ ] 实现 `tool_closures` 属性
  - [ ] 返回工具闭包字典
  - [ ] 检查是否已加载

- [ ] 实现 `get_tools` 方法
  - [ ] 返回工具元组

### 任务 4.2: 实现 `adapter.py` - `load_mcp_tools`

- [ ] 实现 `load_mcp_tools` 函数
  - [ ] 创建并返回 `McpToolsLoader` 实例

### 任务 4.3: 主适配器测试

- [ ] 编写 `McpToolsLoader` 单元测试
  - [ ] 测试完整加载流程
  - [ ] 测试工具过滤
  - [ ] 测试工具名称前缀
  - [ ] 测试资源清理

---

## 开发阶段 5: 测试与文档

### 任务 5.1: 实现 `__init__.py`

- [ ] 导出配置类
  - [ ] `McpServerConfig`
  - [ ] `McpToolFilter`
  - [ ] `McpClientConfig`

- [ ] 导出主函数
  - [ ] `load_mcp_tools`
  - [ ] `McpToolsLoader`

### 任务 5.2: 编写 `README.md`

- [ ] 模块概述
- [ ] 快速开始示例
- [ ] 配置说明
  - [ ] `McpServerConfig` 配置项
  - [ ] `McpToolFilter` 配置项
  - [ ] `McpClientConfig` 配置项
- [ ] API 文档
  - [ ] `load_mcp_tools` 函数
  - [ ] `McpToolsLoader` 类
- [ ] 使用示例
  - [ ] 基本使用
  - [ ] 多 Server 配置
  - [ ] 工具过滤
- [ ] 错误处理说明

### 任务 5.3: 创建测试 MCP Server

- [ ] 创建 `test_mcp_server.py`
  - [ ] 实现 `calculator` 工具
  - [ ] 实现 `slow_tool` 工具
  - [ ] 实现 `error_tool` 工具
  - [ ] 实现多工具 Server

### 任务 5.4: 编写集成测试

- [ ] 创建 `tests/test_mcp_client.py`
  - [ ] 测试单 Server 连接
  - [ ] 测试多 Server 连接
  - [ ] 测试工具过滤
  - [ ] 测试工具调用
  - [ ] 测试错误处理
  - [ ] 测试超时处理

---

## 开发后任务

### 任务 6.1: 代码审查

- [ ] 自我审查代码
  - [ ] 检查代码风格
  - [ ] 检查类型注解
  - [ ] 检查文档字符串

- [ ] 请求他人审查

### 任务 6.2: 性能优化

- [ ] 分析性能瓶颈
- [ ] 优化连接建立时间
- [ ] 优化工具调用延迟

### 任务 6.3: 文档完善

- [ ] 添加更多使用示例
- [ ] 添加故障排除指南
- [ ] 更新项目主文档

### 任务 6.4: 版本发布

- [ ] 更新版本号
- [ ] 编写 CHANGELOG
- [ ] 创建 Git tag

---

## 实施建议

### 开发顺序

按照以下顺序实施可以确保依赖关系正确：

1. **配置模型** → 2. **连接管理** → 3. **工具映射** → 4. **主适配器** → 5. **测试与文档**

### 测试驱动开发

建议采用测试驱动开发（TDD）：

1. 先编写测试用例
2. 实现功能代码
3. 运行测试验证
4. 重构优化

### 迭代开发

可以将每个开发阶段作为一个迭代：

- 迭代 1: 完成配置模型 + 单元测试
- 迭代 2: 完成连接管理 + 单元测试
- 迭代 3: 完成工具映射 + 单元测试
- 迭代 4: 完成主适配器 + 集成测试
- 迭代 5: 完成文档和最终测试

---

## 完成标准

每个任务完成后应满足：

- [ ] 代码实现完成
- [ ] 单元测试通过
- [ ] 代码审查通过
- [ ] 文档更新完成
