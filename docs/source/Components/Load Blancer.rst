Load Blancer
============

负载均衡模块为微服务架构提供智能路由决策。通过策略化设计支持多种负载均衡算法，结合服务注册中心实现动态实例管理。

模块概述
--------

LoadBalancer是负载均衡模块的核心组件，负责根据指定的策略从多个服务实例中选择合适的实例来处理请求。它提供了自动重试机制和错误处理功能，确保服务的高可用性。

核心组件
--------

1. `LoadBalancer` - 核心控制器协调策略与注册中心
2. `LoadBalanceStrategy` - 抽象基类定义统一的策略接口
3. `ServiceRegistry` - 服务注册中心访问接口
4. `ServiceInstanceBase` - 服务实例的基础抽象类
5. `ServiceConfig` - 服务特定配置容器

LoadBalancer类
--------------

.. class:: LoadBalancer(registry, strategy_type=RoundRobinStrategy)

   负载均衡核心控制器。

   :param registry: ServiceRegistry 实例，用于管理服务实例
   :param strategy_type: LoadBalanceStrategy 类型，默认为 RoundRobinStrategy

   .. method:: execute(service_name, request_func, override_config=None)

      执行负载均衡请求。
      当发生 `RequestTimeoutError`、 `ServiceError` 或 `LimitExceededError` 异常时，LoadBalancer会根据配置自动重试，直到达到最大重试次数。

      :param service_name: 注册的服务名称
      :param request_func: 实际请求的函数 (接受ServiceInstance参数)
      :param override_config: 可覆盖的配置
      :return: 请求结果
      :raises NoAvailableInstanceError: 当没有可用的服务实例时抛出
      :raises MaxRetriesExceededError: 当超过最大重试次数时抛出

ServiceRegistry类
-----------------

.. class:: ServiceRegistry()

   服务注册中心，用于管理服务实例和配置。每个服务对应一个重试配置, 对应多个服务实例。

   .. method:: register_service(service_name, instance)

      注册服务实例。

      :param service_name: 服务名称
      :param instance: ServiceInstanceBase 实例

   .. method:: set_service_config(service_name, config)

      设置服务配置。

      :param service_name: 服务名称
      :param config: ServiceConfig 实例

   .. method:: get_instances(service_name)

      获取服务实例列表。

      :param service_name: 服务名称
      :return: ServiceInstanceBase 实例列表

   .. method:: get_config(service_name)

      获取服务配置。

      :param service_name: 服务名称
      :return: ServiceConfig 实例


ServiceConfig类
----------------

.. class:: ServiceConfig(max_retries=100, retry_delay=2, retry_backoff=1.1)

   服务特定重试配置容器。

   :param max_retries: 最大重试次数，默认为100
   :param retry_delay: 重试基础延迟(秒)，默认为2秒
   :param retry_backoff: 退避因子，默认为1.1

使用示例
--------

.. code-block:: python

   from api.load_balance import LOAD_BLANCER, QWEN_MAX_SERVICE_NAME
   from api.llm.generator import DEFAULT_RETRY_CONFIG
   from api.load_balance.delegate.openai import generation_delegate_for_async_openai

   # 创建消息列表
   messages = [...]
   # 创建重试配置
   retry_configs = ...
   # 其他参数
   kwargs = {...}

   # 定义闭包
   async def delegate(instance):
       # other logic here
       return await generation_delegate_for_async_openai(
           instance,
           messages,
           DEFAULT_RETRY_CONFIG
           **kwargs
       ) # if this func throws an error in [ `RequestTimeoutError`, `ServiceError`, `LimitExceededError`], the load balancer will retry

   # 执行请求
   result = await LOAD_BLANCER.execute(
       QWEN_MAX_SERVICE_NAME,
       delegate,
   )

策略类型
--------

1. `RoundRobinStrategy` - 轮询选择策略（默认）
   依次选择服务实例，确保请求均匀分布到所有实例上。

2. `RandomStrategy` - 随机选择策略
   随机选择一个服务实例来处理请求。

异常处理
--------

负载均衡模块定义了以下异常类型：

1. `NoAvailableInstanceError` - 没有可用的服务实例
2. `RequestTimeoutError` - 请求超时
3. `LimitExceededError` - 限制超出错误
4. `ServiceError` - 服务错误
5. `MaxRetriesExceededError` - 超过最大重试次数

推荐思路
-------

我们推荐按如下思路对应抽象和实际需求：

1. 将某种语言模型型号对应为服务A。
2. 将调用某家云服务商的所有必要配置对应为一个服务实例注册到服务A中。
3. 传入一个委托到LoadBalancer的execute函数，在适当的时候抛出异常，触发重试以完成负载均衡。