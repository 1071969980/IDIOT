Human In The Loop （HIL）
==============================

人类交互模块为应用提供了一种基于人类反馈的运行方式，同时也被用作应用发起远程工具调用或日志通知。

**重要更新**: 本模块目前主要使用 **HTTP 长轮询** 协议进行客户端与服务器的通信。WebSocket 协议仍然保留但已标记为废弃状态。

主要代码位于 ``api/human_in_loop``

**主要组件**：
- **HTTP Worker**: 主要的通信组件，提供长轮询API端点
- **Redis Stream**: 消息存储和传递的核心机制
- **Context Manager**: 管理Redis消息流的创建和生命周期
- **Interrupt/Notification**: 向用户发送中断请求和通知消息的接口


主要行为时序图
------------------

.. mermaid::
    :zoom:
    :caption: HTTP 长轮询模式的HIL交互时序图

    sequenceDiagram

        actor user
        participant app as Application
        participant http as HTTP API
        participant rd as Redis

        user ->> app: login
        app -->> user: token

        user ->> app: invoke something

        create participant ctx as HILMessageStreamContext
        app ->> ctx: with HILMessageStreamContext(session_id)
        app -->> user: session_id

        opt Many Times HIL

            create participant int as interrupt()

            app ->> int: await interrupt(content)
            activate app

            int ->> rd: Write content to redis stream
            activate int

            loop Client Polling
                user ->> http: POST /hil/poll (with session_id, last_id)
                http ->> rd: Read message from redis stream
                rd -->> http: Return HIL message
                http -->> user: Return HILPollResponse
            end

            Note over user: Process interrupt request
            user ->> http: POST /hil/respond (with msg_id, response)
            http ->> rd: Write response to redis stream

            rd -->> int: Read response from redis stream
            deactivate int

            destroy int
            int -->> app: Return human feedback content


        end

        deactivate app

        destroy ctx
        app ->> ctx: exit

**主要角色**：

1. **Application**: 表示你的整个应用程序，向用户提供服务。
2. **HTTP API**: 长轮询API服务，提供消息轮询和响应端点。主要接口包括 `/hil/poll` 和 `/hil/respond`。
3. **Redis**: 用于HIL功能中存储消息流，确保消息的可靠传递。
4. **HILMessageStreamContext**: Python上下文管理器，用于管理Redis消息流的创建和生命周期。
5. **interrupt()**: 异步函数，用于等待用户交互和反馈。

**主要流程（HTTP 长轮询模式）**：

1. 用户登录获取JWT令牌。
2. 用户调用某个需要HIL的服务（需要JWT令牌验证）。
3. 应用生成SessionID（或任何能够标识该用户的该次调用的ID），调用HILMessageStreamContext时传入SessionID创建Redis消息流。
4. 应用返回SessionID给用户。
5. 客户端开始长轮询循环：
    1. 应用调用interrupt()函数，等待用户交互。传入HILInterruptContent格式的内容和SessionID。
    2. interrupt()函数将内容序列化后写入Redis发送流。
    3. 客户端通过 `/hil/poll` 端点轮询消息，携带SessionID和最后读取的消息ID。
    4. HTTP API从Redis发送流中读取消息并返回给客户端。
    5. 用户处理中断请求，准备响应内容。
    6. 客户端通过 `/hil/respond` 端点发送响应，携带原始消息ID和响应内容。
    7. HTTP API将响应写入Redis接收流。
    8. interrupt()函数从Redis接收流中读取匹配的响应消息。
    9. interrupt()函数将响应返回给应用。
6. 应用退出HILMessageStreamContext，自动销毁Redis消息流。
7. 客户端检测到消息流不存在后停止轮询。

interrupt
---------------

``interrupt()`` 函数用于等待用户交互和反馈。

.. function:: interrupt(content, stream_identifier,[timeout=3600, timeout_retry=6, cancel_event=None])
    :async:

    :param content: 将发送给客户端的中断内容，必须符合HILInterruptContent格式。包含source字段和body字段。
    :type content: HILInterruptContent
    :param stream_identifier: 要监听的Redis消息流的标识符。由应用生成，并作为参数传入。
    :type stream_identifier: str
    :param timeout: 超时时间，单位为秒。
    :type timeout: int
    :param timeout_retry: 超时重试次数。超出重试次数后，将抛出异常。
    :type timeout_retry: int
    :param cancel_event: 可选传入一个asyncio的Event信号量，用于取消任务。取消会抛出异常。
    :type cancel_event: asyncio.Event

    :return: 用户返回的数据，通常为字符串或字典格式，具体内容由应用和客户端约定。

    :raises ValueError: 如果content参数不是HILInterruptContent类型。
    :raises HILMsgStreamMissingError: 如果stream_identifier指向的Redis消息流不存在或已过期。
    :raises HILInterruptCancelled: 如果超时或cancel_event被触发，将抛出此异常。


数据血缘图
~~~~~~~~~~~~

.. mermaid::
    :zoom:
    :caption: interrupt() 函数的数据处理流程

    graph TD
        content["content: HILInterruptContent"]
        p_d(["pickle.dumps(content)"])
        HIL["HIL_RedisMsg.content: bytes"]
        p_l(["pickle.loads(content)"])
        response["用户响应: str | dict"]

        content --> p_d
        p_d --> HIL
        HIL --> p_l
        p_l --> response

数据模型转换关系
~~~~~~~~~~~~~~~~

**interrupt 函数到 /hil/poll 接口的数据转换**

``interrupt()`` 函数的 ``content`` 参数与 ``/hil/poll`` 接口返回数据之间存在序列化-反序列化的转换关系：

**1. 输入数据模型 (interrupt 函数)**

``interrupt()`` 函数接收结构化的 Pydantic 模型：

.. code-block:: python

    class HILInterruptContent(BaseModel):
        source: Literal["agent_tool_call"]
        body: HILInterruptContentAgentToolCallBody

    class HILInterruptContentAgentToolCallBody(BaseModel):
        tool_name: str
        type: HILInterruptContentAgentToolCallBodyType  # 如 "ChoiceForm"
        tool_exec_uuid: str
        detail: Any  # 必须可JSON序列化

**2. 传输序列化过程**

1. **序列化**: ``pickle.dumps(content)`` 将 Pydantic 模型序列化为字节数据
2. **存储**: 作为 ``HIL_RedisMsg.content`` 存储到 Redis 发送流
3. **读取**: ``LongPollWorker`` 从 Redis 流中读取消息
4. **反序列化**: ``pickle.loads()`` 恢复为原始对象
5. **JSON转换**: 如果是 BaseModel，调用 ``model_dump(mode="json")`` 转换为字典

**3. 输出数据结构 (/hil/poll 接口)**

客户端通过 ``/hil/poll`` 接口接收到的数据格式：

.. code-block:: json

    {
        "redis_last_id": "1678886400001-0",
        "HIL_msg": {
            "msg_id": "7c21ea75-0035-48e0-9944-41a8e0077c2f",
            "msg_type": "HIL_interrupt_request",
            "content": {
                "source": "agent_tool_call",
                "body": {
                    "tool_name": "search_web",
                    "type": "ChoiceForm",
                    "tool_exec_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "detail": {...}
                }
            }
        }
    }

**4. 数据完整性保证**

- **结构保持**: ``source`` 和 ``body`` 字段在转换过程中完全一致
- **类型安全**: Pydantic 模型确保输入数据的类型和格式正确
- **JSON兼容**: 最终输出为 JSON 兼容的字典格式，便于客户端处理
- **数据验证**: ``detail`` 字段必须可 JSON 序列化，确保传输可靠性

**5. 关键转换代码位置**

在 ``api/human_in_loop/http_worker/long_poll_worker.py:141-144`` 中：

.. code-block:: python

    msg_content = pickle.loads(msg_data[b"content"])
    if isinstance(msg_content, BaseModel):
        msg_content = msg_content.model_dump(mode="json")

这种设计确保了类型安全的服务端处理和易于使用的客户端数据格式之间的平衡。

notification
-------------

``notification()`` 函数用于发送通知给用户，不需要等待响应。

.. function:: notification(content, stream_identifier)
    :async:

    :param content: 将发送给客户端的通知消息，必须为pydantic的BaseModel的子类。
    :type content: pydantic.BaseModel
    :param stream_identifier: 要监听的Redis消息流的标识符。由应用生成，并作为参数传入。
    :type stream_identifier: str

    :return: None

    :raises ValueError: 如果content参数不是pydantic.BaseModel的子类。
    :raises HILMsgStreamMissingError: 如果stream_identifier指向的Redis消息流不存在或已过期。

HTTP API 长轮询协议
-------------------

HIL 模块主要使用 HTTP 长轮询协议进行客户端与服务器的通信。该协议基于标准的 HTTP REST API，客户端通过轮询获取消息，通过 POST 请求发送响应。

HTTP API 端点
~~~~~~~~~~~~~~

HIL 模块提供两个主要的 HTTP API 端点：

1. **POST /hil/poll** - 轮询消息端点
2. **POST /hil/respond** - 发送响应端点

认证方式
~~~~~~~~

所有 HTTP API 端点都需要 JWT 认证。客户端需要在请求头中包含有效的 JWT token：

.. code-block:: http

    Authorization: Bearer <jwt-token>

轮询消息接口
~~~~~~~~~~~~

**端点**: ``POST /hil/poll``

**请求体**:

.. code-block:: json

    {
        "session_task_id": "550e8400-e29b-41d4-a716-446655440000",
        "timeout": 30,
        "redis_last_id": "1678886400000-0"
    }

**响应体**:

.. code-block:: json

    {
        "redis_last_id": "1678886400001-0",
        "HIL_msg": {
            "msg_id": "7c21ea75-0035-48e0-9944-41a8e0077c2f",
            "msg_type": "HIL_interrupt_request",
            "content": {
                "source": "agent_tool_call",
                "body": {
                    "tool_name": "search_web",
                    "type": "ChoiceForm",
                    "tool_exec_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "detail": {...}
                }
            }
        }
    }

**无消息时**: 返回 HTTP 204 状态码

发送响应接口
~~~~~~~~~~~~

**端点**: ``POST /hil/respond``

**请求体**:

.. code-block:: json

    {
        "session_task_id": "550e8400-e29b-41d4-a716-446655440000",
        "hil_msg_id": "7c21ea75-0035-48e0-9944-41a8e0077c2f",
        "msg": "用户选择的响应内容"
    }

**响应**: HTTP 200 状态码，无内容

数据模型
~~~~~~~~

**HILPollRequest**:

.. code-block:: python

    class HILPollRequest(BaseModel):
        session_task_id: uuid.UUID
        timeout: int = 30
        redis_last_id: str = "0"

**HILPollResponse**:

.. code-block:: python

    class HILPollResponse(BaseModel):
        redis_last_id: str
        HIL_msg: dict[str, Any] | None

**HILResponseRequest**:

.. code-block:: python

    class HILResponseRequest(BaseModel):
        session_task_id: uuid.UUID
        hil_msg_id: str
        msg: str | dict

**HILInterruptContent**:

.. code-block:: python

    class HILInterruptContent(BaseModel):
        source: Literal["agent_tool_call"]
        body: HILInterruptContentAgentToolCallBody

客户端工作流程
~~~~~~~~~~~~~~

1. **获取消息**: 客户端定期调用 ``/hil/poll`` 端点
2. **处理中断**: 收到 ``HIL_interrupt_request`` 类型消息时，显示给用户
3. **发送响应**: 用户做出选择后，调用 ``/hil/respond`` 端点发送响应
4. **处理通知**: 收到 ``Notification`` 类型消息时，直接显示给用户，无需响应

消息确认机制
~~~~~~~~~~~~

HTTP 模式下使用基于 Redis 消息 ID 的确认机制：

1. 消息被读取后，系统会记录 ``redis_last_id``
2. 下次轮询时，使用该 ID 获取新消息
3. 发送响应时，需要提供原始消息的 ``msg_id``
4. 系统自动处理消息的生命周期管理

错误处理
~~~~~~~~

HTTP API 使用标准的 HTTP 状态码和 JSON 错误响应：

**常见 HTTP 状态码**：

- ``200``: 成功
- ``204``: 无消息内容（轮询超时）
- ``400``: 请求参数错误
- ``401``: 未授权（JWT token 无效）
- ``404``: 资源不存在（消息流过期）
- ``500``: 服务器内部错误

**错误响应格式**:

.. code-block:: json

    {
        "detail": "错误描述信息"
    }

**常见错误类型**：

- Stream 不存在或已过期
- JWT token 认证失败
- 请求参数格式错误
- 消息 ID 不匹配

客户端实现要点
~~~~~~~~~~~~~~

1. **轮询管理**：
   - 实现适当的轮询间隔（推荐 1-5 秒）
   - 处理网络超时和重连逻辑
   - 根据业务需求调整轮询频率

2. **状态管理**：
   - 维护 ``redis_last_id`` 来跟踪消息位置
   - 处理会话生命周期（创建、活跃、销毁）
   - 管理待处理的用户中断请求

3. **用户界面**：
   - 区分中断请求和通知消息
   - 为不同类型的 ``HILInterruptContent`` 提供合适的界面
   - 实现用户友好的响应输入方式

4. **错误处理**：
   - 处理 HTTP 错误响应和网络异常
   - 实现指数退避的重连策略
   - 提供用户友好的错误提示

5. **性能优化**：
   - 避免过于频繁的轮询请求
   - 使用长连接池优化网络性能
   - 合理设置超时时间

WebSocket 备用协议（已废弃）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**注意**: WebSocket 协议实现仍然存在但已标记为废弃状态，不建议在新项目中使用。如需了解细节，请参考源代码中的 ``ws_worker`` 目录。

安全考虑
~~~~~~~~

1. **JWT 认证**: 所有 API 调用都需要有效的 JWT token
2. **会话隔离**: 每个 session_task_id 对应独立的 Redis 消息流
3. **自动过期**: Redis 消息流具有自动过期机制（默认 3600 秒）
4. **数据验证**: 所有输入数据都经过严格的类型和格式验证
5. **权限控制**: 只能访问自己授权的消息流和会话