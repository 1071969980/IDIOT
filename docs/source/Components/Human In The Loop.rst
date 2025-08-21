Human In The Loop （HIL）
==============================

人类交互模块为应用提供了一种基于人类反馈的运行方式。同时也被用作应用发起远程工具调用或是日志通知。
主要代码位于 ``api/human_in_the_loop``


主要行为时序图
------------------

.. mermaid::
    :zoom:
    :caption: 图上角色的激活代表异步函数的等待

    sequenceDiagram

        actor user
        participant ws as WebSocket
        participant app as Application
        participant rd as Redis

        user ->> app: login
        app -->> user: token

        user ->> app: invoke something

        create participant ctx as HILMessageStreamContext
        app ->> ctx: with HILMessageStreamContext(session_id)
        app -->> user: session_id

        user ->> ws: connect 
        user ->> ws: auth and init
        
        opt Many Times HIL

            create participant int as interrupt()

            app ->> int: await interrupt(msg)
            activate app

            int ->> rd: Write msg to redis stream
            activate int

            rd ->> ws: Read message from redis stream
            ws ->> user: Send message in JSON-RPC format

            user ->> ws: Response message in JSON-RPC format
            ws ->> rd: Write response to redis stream
            
            rd -->> int: Read msg from redis stream
            deactivate int

            destroy int
            int -->> app: Return human feedback msg
            

        end
        
        deactivate app
        
        destroy ctx
        app ->> ctx: exit

**主要角色**：

1. **Application**: 表示你的整个应用程序，向用户提供服务。
2. **WebSocket**: 单独启动的进程，用于HIL功能中与客户端保持双向交互。
3. **Redis**: 用于HIL功能中存储消息流。以确保消息的送达。
4. **HILMessageStreamContext**: python上下文管理器，用于管理Redis的消息流的创建和销毁。
5. **interrupt()**: 异步函数，用于等待用户交互

**主要流程**：

1. 用户登陆获取JWT令牌。
2. 用户调用某个需要HIL的服务。(可能需要JWT令牌验证)
3. 应用生成SessionID（或者任何能够标识该用户的该次调用的id），调用HILMessageStreamContext时传入SessionID创建Redis消息流。
4. 应用返回SessionID给用户。
5. 用户端提前知道该次调用需要HIL，并连接WebSocket。
6. 按约定在WebSocket中发送认证和初始化消息。
7. 循环：
    1. 应用调用interrupt()函数，等待用户交互。传入消息和SessionID。
    2. interrupt()函数将消息写入Redis消息流。
    3. WebSocket从Redis消息流中读取消息。
    4. WebSocket将消息发送给用户。
    5. 用户响应消息。
    6. WebSocket将用户响应消息写入Redis消息流。
    7. interrupt()函数从Redis消息流中读取消息。
    8. interrupt()函数返回给应用。
8. 应用退出HILMessageStreamContext，销毁Redis消息流。
9. 用户主动断开WebSocket连接。或者等待Redis消息流销毁后，自动超时断开连接。

interrupt
---------------

``interrupt()`` 函数用于等待用户交互。

.. function:: interrupt(msg, stream_identifier,[timeout=3600, timeout_retry=6, cancel_event=None])
    :async:

    :param msg: 将发送给客户端的消息，最终将被处理为json格式发送。必须为pydantic的BaseModel的子类。
    :type msg: pydantic.BaseModel
    :param stream_identifier: 要监听的Redis消息流的标识符。由应用生成，并作为参数传入。
    :type stream_identifier: str
    :param timeout: 超时时间，单位为秒。
    :type timeout: int
    :param timeout_retry: 超时重试次数。超出重试次数后，将抛出异常。
    :type timeout_retry: int
    :param cancel_event: 可选传入一个asyncio的Event信号量，用于取消任务。取消会抛出异常。
    :type cancel_event: asyncio.Event

    :return: 用户返回的数据，自行约定数据内容，一般是字符串或者是从json解析的字典。

    :raises ValueError: 如果msg参数不是pydantic的BaseModel的子类。
    :raises HILMsgStreamMissingError: 如果stream_identifier指向的Redis消息流不存在。
    :raises HILInterruptCancelled: 如果超时或cancel_event被触发，将抛出此异常。


.. mermaid::
    :zoom:
    :caption: 数据血缘

    graph TD
        msg["msg: pydantic.BaseModel"]
        p_d(["pickle.dumps(msg)"])
        HIL["HIL_RedisMsg.msg: bytes"]
        p_l(["pickle.loads(HIL_RedisMsg.msg)"])
        rpc["JsonRPCRequest.params.msg: dict"]

        msg --> p_d
        p_d --> HIL
        HIL --> p_l
        p_l --> rpc

notification
-------------

``notification()`` 函数用于发送通知给用户。

.. function:: notification(msg, stream_identifier)
    :async:

    :param msg: 将发送给客户端的消息，最终将被处理为json格式发送。必须为pydantic的BaseModel的子类。
    :type msg: pydantic.BaseModel
    :param stream_identifier: 要监听的Redis消息流的标识符。由应用生成，并作为参数传入。
    :type stream_identifier: str

    :return: None

WebSocket 通讯协议
------------------

HIL 模块使用 JSON-RPC 2.0 协议进行 WebSocket 通信。协议支持请求-响应模式，并包含消息确认机制。

协议基础
~~~~~~~~

所有消息都遵循 JSON-RPC 2.0 格式：

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "unique-request-id",
        "method": "method-name",
        "params": {
            "param1": "value1",
            "param2": "value2"
        }
    }

响应格式：

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "request-id",
        "result": "ack",
        "error": null
    }

连接初始化
~~~~~~~~~~

1. 客户端连接到 WebSocket 服务器
2. 发送初始化请求：

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "client-init-id",
        "method": "initialize",
        "params": {
            "auth_token": "jwt-token",
            "stream_identifier": "session-id"
        }
    }

3. 服务器验证 JWT token 和 stream_identifier
4. 服务器返回确认响应：

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "client-init-id",
        "result": "ack"
    }

消息类型
~~~~~~~~

**服务器到客户端的请求：**


.. mermaid::
    :zoom:
    :caption: 消息类型交互时序图

    sequenceDiagram

        participant S as 服务器
        participant C as 客户端

        Note over S,C: 中断请求流程

        S->>C: HIL_interrupt_request<br/>(id, msg_id, msg)
        C->>S: ack<br/>(id)
        Note over C: 处理用户输入
        C->>S: HIL_interrupt_response<br/>(new_id, msg_id, response)
        S->>C: ack<br/>(new_id)

        Note over S,C: 通知流程

        S->>C: Notification<br/>(id, content)
        C->>S: ack<br/>(id)


1. **HIL_interrupt_request** - 中断请求
   - 当应用调用 ``interrupt()`` 时触发
   - 需要客户端返回响应

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "server-request-id",
        "method": "HIL_interrupt_request",
        "params": {
            "msg_id": "unique-message-id",
            "msg": {"message": "content"}  # JSON 格式的消息内容
        }
    }

2. **Notification** - 通知消息
   - 当应用调用 ``notification()`` 时触发
   - 不需要响应

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "server-request-id",
        "method": "Notification",
        "params": {"notification": "content"}
    }

**客户端到服务器的响应：**

1. **Ack 响应** - 确认收到请求
   - 必须在收到请求后立即发送

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "server-request-id",
        "result": "ack"
    }

2. **HIL_interrupt_response** 中断回复
   - 对 HIL_interrupt_request 的响应

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "client-response-id",
        "method": "HIL_interrupt_response",
        "params": {
            "msg_id": "original-message-id",
            "msg": {"response": "content"}  # JSON 格式的响应内容
        }
    }

消息确认机制
~~~~~~~~~~~~

1. 服务器维护未确认消息队列 (``un_ack_msg``)
2. 每 5 秒重发未确认的消息
3. 客户端收到请求后必须立即发送 ack 响应
4. 服务器收到 ack 后从队列中移除对应消息

错误处理
~~~~~~~~

协议使用标准的 JSON-RPC 2.0 错误码：

- ``-32700``: 解析错误
- ``-32600``: 无效请求
- ``-32601``: 方法不存在
- ``-32602``: 无效参数
- ``-32603``: 内部错误

错误响应格式：

.. code-block:: json

    {
        "jsonrpc": "2.0",
        "id": "request-id",
        "error": {
            "code": -32602,
            "message": "Invalid parameters"
        }
    }

客户端实现要点
~~~~~~~~~~~~~~

1. **连接管理**：
   - 维护连接状态
   - 处理重连逻辑
   - 管理后台任务

2. **消息处理**：
   - 使用异步任务处理并发请求
   - 区分请求和响应
   - 维护待响应的请求 ID 列表

3. **回调机制**：
   - 注册中断请求的回调函数
   - 异步处理用户输入
   - 构造并发送响应

4. **错误处理**：
   - 捕获并记录连接错误
   - 处理消息解析错误
   - 实现超时机制

客户端实现示例位于 ``./examples/human_in_loop_client.py``

安全考虑
~~~~~~~~

1. 所有连接都需要 JWT token 认证
2. 每个会话都有唯一的 stream_identifier
3. Redis 消息流有自动过期机制
4. WebSocket 连接有超时断开机制