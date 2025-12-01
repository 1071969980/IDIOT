Logger System
=============

AI应用开发中可观测性是不可或缺的组件，用于监控、调试和分析系统行为。本工具箱采用 OpenTelemetry、Jaeger 和 Prometheus 构建了一套完整的可观测性解决方案。

系统架构
--------

整个日志系统由以下几个核心组件构成：

1. **OpenTelemetry Collector (otel_collector)** - 作为遥测数据的中央收集器和分发器
2. **Jaeger** - 分布式追踪系统，用于可视化请求在系统中的流转过程
3. **Prometheus** - 监控和告警工具包，用于收集和查询指标数据

工作流程
--------

数据流向如下：

1. 应用程序通过 logfire 生成遥测数据（traces、metrics、logs）
2. OpenTelemetry Collector 接收来自应用程序的 OTLP 数据
3. Collector 根据配置将数据分发到不同的后端系统：
   - 追踪数据发送到 Jaeger
   - 指标数据发送到 Prometheus
4. Jaeger 和 Prometheus 分别存储和展示各自的数据
5. 用户可以通过 Web UI 查看和分析数据（见 :doc:`../User Guide/Deploy` ）

OpenTelemetry Collector 详解
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

OpenTelemetry Collector 是整个日志系统的核心组件，负责接收、处理和转发遥测数据。

配置文件：``otel_collector/otel-collector-config-connector.yml``

Jaeger 详解
~~~~~~~~~~~

Jaeger 是 Uber 开发的端到端分布式追踪系统，用于监控和诊断基于微服务的分布式系统。

配置文件：``jaeger/config.yaml``

Prometheus 详解
~~~~~~~~~~~~~~~

Prometheus 是一个开源的系统监控和告警工具包，特别适合记录纯数字时间序列数据。

配置文件：``prometheus/prometheus-config.yaml``

应用程序集成
------------

应用程序通过以下方式集成到日志系统：

1. **环境变量配置**:
   - ``LOGFIRE_LOG_ENDPOINT`` 设置为 http://otel_collector:4318

2. **python logfire库集成**:
   - 使用 logfire 库生成追踪数据
   - 自动将跨度信息发送到配置的端点

3. **自定义装饰器**:
   - 提供 ``log_span`` 装饰器用于方便的添加跨度信息

数据流示例
----------

1. 应用程序调用被 ``log_span`` 装饰的函数, 或者是直接调用 logfire 库生成追踪数据
2. OpenTelemetry SDK 生成追踪跨度
3. 数据通过 OTLP 协议发送到 otel_collector:4318
4. OpenTelemetry Collector 处理数据:
   - 将追踪数据转发给 langfuse
   - 将指标数据暴露给 Prometheus 抓取
   - 通过 spanmetrics 生成额外的服务指标
5. langfuse 存储并展示追踪数据
6. Prometheus 抓取并存储指标数据

log_span 装饰器详解
-------------------

``log_span`` 装饰器是本系统提供的一个用于创建分布式追踪跨度的工具函数，它基于 OpenTelemetry 和 logfire 实现。

主要功能：

1. **创建追踪跨度**：为被装饰的函数自动创建一个追踪跨度(span)
2. **参数捕获**：可以将指定的函数参数作为标签附加到跨度上
3. **支持同步和异步函数**：自动识别函数类型并应用相应的包装器
4. **与日志系统集成**：生成的跨度会自动发送到 OpenTelemetry Collector

使用方法：

.. code-block:: python

   @log_span("处理用户请求", args_captured_as_tags=['user_id'], only_tags_kwargs=['!uuid'])
   def handle_request(user_id: int):
       # 函数执行时会产生名为"处理用户请求"的 span
       # 并附带标签 {'user_id': 实际参数值}
       pass

   # 调用时可以传递仅作为标签使用的参数
   handle_request(user_id=123, **{"!uuid": "fd0bc3b2-934a-41e4-b623-afa3435a4cc3"})

参数说明：

- ``message``：跨度的描述信息，将作为 span 名称显示
- ``args_captured_as_tags``：需要捕获并作为 span 标签的函数参数名列表
- ``only_tags_kwargs``：仅作为标签使用而不传递给函数的参数名列表（需要以"!"开头）
- ``forward_to_loguru``：是否将跨度信息转发到 loguru 日志系统