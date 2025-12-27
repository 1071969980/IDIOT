# Dynamic Tool DI 开发任务指南

## 快速理解

Dynamic Tool DI 是什么？
一个让 LLM 代理能参与程序执行的动态工具注入系统。

核心解决的问题：
- 如何让 AI 决策影响程序执行流程
- 如何在运行时动态创建工具供 AI 调用
- 如何安全地将 AI 的决策转化为程序动作

## 核心接口

### construct_tool 函数
这是整个系统的核心，你必须掌握：

```python
def construct_tool(
    tool_name: str,
    tool_description: str,
    tool_param_model: type[BaseModel],
    call_back: Callable[[BaseModel], Coroutine[Any, Any, None]],
) -> tuple[ChatCompletionToolParam, ToolClosure]
```

**输入什么：**
1. `tool_name` - AI 调用时用的工具名
2. `tool_description` - 告诉 AI 这个工具干什么
3. `tool_param_model` - Pydantic 模型，定义参数结构
4. `call_back` - 你的业务逻辑函数

**输出什么：**
1. 工具定义（给 AI 看的）
2. 工具闭包（程序实际执行的）

## 开发任务类型

### 任务1：创建新的动态工具

**步骤：**
1. 定义参数模型（继承 BaseModel）
2. 编写回调函数（处理业务逻辑）
3. 调用 construct_tool
4. 将工具注册到代理

**标准模板：**
```python
# 1. 定义参数模型
class YourToolParamDefine(BaseModel):
    input_data: str = Field(..., description="输入数据")
    option: str = Field(default="default", description="可选配置")

# 2. 编写回调函数（使用 def 定义，不要使用 lambda）
# 注意：参数类型注解必须是 BaseModel，而不是具体子类
# 这是因为 Callable 的参数类型是逆变的（contravariant）
async def your_callback(param: BaseModel) -> None:
    # 类型检查：确保参数是预期的子类类型
    if not isinstance(param, YourToolParamDefine):
        raise TypeError(
            f"Expected YourToolParamDefine, got {type(param).__name__}"
        )

    # 你的业务逻辑（现在可以安全地访问子类的字段）
    result = process_data(param.input_data, param.option)
    # 存储结果到外部变量或返回
    your_result_container["output"] = result

# 3. 构造工具
tool_define, tool_closure = construct_tool(
    "your_tool_name",
    "工具功能描述",
    YourToolParamDefine,
    your_callback
)
```

### 任务2：集成到现有代理

**关键点：**
- 工具定义加入 `tools` 列表
- 工具闭包加入 `tool_call_function` 字典
- 确保工具名与字典键一致

**集成模式：**
```python
agent = AgentBase(
    tools=[tool_define],  # 工具定义列表
    tool_call_function={
        "your_tool_name": tool_closure  # 工具名 -> 执行闭包
    }
)
```

### 任务3：处理工具执行结果

**结果容器模式：**
由于回调函数通过副作用传递结果，需要使用外部容器：

```python
# 结果容器
result_container = {"output": "", "error": None}

async def callback(param: YourToolParamDefine):
    try:
        result_container["output"] = your_logic(param)
    except Exception as e:
        result_container["error"] = str(e)

# 执行后检查结果
if result_container["error"]:
    # 处理错误
else:
    # 使用 result_container["output"]
```

**重试机制：**
```python
max_attempts = 3
attempt = 0

while attempt < max_attempts and not result_container["output"]:
    await agent.run(memories, service_name)
    attempt += 1

if not result_container["output"]:
    raise ValueError("工具执行失败")
```

## 开发规范

### 参数模型设计
- **必须继承 BaseModel**
- **每个字段都要有 description**
- **使用合适的 Field 类型约束**
- **提供合理的默认值**

### 回调函数设计
- **必须是 async 函数**
- **参数类型注解必须是 BaseModel**（由于 Callable 参数类型的逆变性）
- **在函数内部使用 isinstance 检查实际的子类类型**
- **类型检查失败时抛出合适的运行时异常**
- **通过外部容器返回结果**
- **做好异常处理**
- **避免使用 lambda 创建闭包，使用 def 定义异步函数**

### 工具命名规范
- **使用下划线命名法**
- **名称要描述工具功能**
- **避免与现有工具冲突**

## 常见开发场景

### 场景1：状态总结工具
让 AI 分析当前状态并给出结论

```python
class StatusConclusionParamDefine(BaseModel):
    conclusion: str = Field(..., description="当前状态的结论")

result = {"conclusion": ""}

async def conclusion_callback(param: BaseModel) -> None:
    # 类型检查
    if not isinstance(param, StatusConclusionParamDefine):
        raise TypeError(
            f"Expected StatusConclusionParamDefine, got {type(param).__name__}"
        )
    result["conclusion"] = param.conclusion
```

### 场景2：指导生成工具
让 AI 生成下一步执行指导

```python
class GuidanceParamDefine(BaseModel):
    guidance: str = Field(..., description="执行指导建议")

guidance_result = {"guidance": ""}

async def guidance_callback(param: BaseModel) -> None:
    # 类型检查
    if not isinstance(param, GuidanceParamDefine):
        raise TypeError(
            f"Expected GuidanceParamDefine, got {type(param).__name__}"
        )
    guidance_result["guidance"] = param.guidance
```

### 场景3：数据处理工具
让 AI 参与数据处理决策

```python
class DataProcessParamDefine(BaseModel):
    data: dict = Field(..., description="待处理数据")
    action: str = Field(..., description="处理动作")

process_result = {"output": None}

async def process_callback(param: BaseModel) -> None:
    # 类型检查
    if not isinstance(param, DataProcessParamDefine):
        raise TypeError(
            f"Expected DataProcessParamDefine, got {type(param).__name__}"
        )
    process_result["output"] = apply_action(param.data, param.action)
```

## 调试技巧

### 1. 验证工具定义
```python
# 检查生成的工具定义
print(f"Tool name: {tool_define['function']['name']}")
print(f"Tool description:
{tool_define['function']['description']}")
print(f"Parameters schema:
{tool_define['function']['parameters']}")
```

### 2. 监控执行过程
```python
# 在回调中添加日志
async def callback(param: BaseModel) -> None:
    # 类型检查
    if not isinstance(param, YourToolParamDefine):
        raise TypeError(
            f"Expected YourToolParamDefine, got {type(param).__name__}"
        )

    logger.info(f"Tool called with params: {param}")
    try:
        # 业务逻辑
        logger.info("Tool execution completed successfully")
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        raise
```

### 3. 检查结果容器
```python
# 确保结果容器有初始值
result_container = {"output": None, "error": None}

# 执行后检查
if result_container["error"]:
    print(f"Error: {result_container['error']}")
if result_container["output"] is None:
    print("Warning: No output generated")
```

## 错误处理

### 常见错误类型
1. **参数验证失败** - 检查模型定义和传入数据
2. **回调函数异常** - 确保异常处理完善
3. **结果容器未初始化** - 检查容器初始状态
4. **工具注册错误** - 验证工具名和映射关系

### 错误处理模式
```python
# 在回调中处理异常
async def safe_callback(param: BaseModel) -> None:
    # 类型检查
    if not isinstance(param, YourToolParamDefine):
        raise TypeError(
            f"Expected YourToolParamDefine, got {type(param).__name__}"
        )

    try:
        # 业务逻辑
        result_container["output"] = process(param)
    except ValidationError as e:
        result_container["error"] = f"参数验证失败: {e}"
    except BusinessLogicError as e:
        result_container["error"] = f"业务逻辑错误: {e}"
    except Exception as e:
        result_container["error"] = f"未知错误: {e}"
```

## 性能考虑

### 优化建议
1. **避免重复构造工具** - 缓存工具定义
2. **控制回调执行时间** - 设置合理超时
3. **限制并发执行** - 避免资源竞争
4. **合理设计参数** - 避免过大的数据传输