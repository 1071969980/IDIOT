Project Structure
=================

.. code-block:: text

    IDIOT
    ├── api # 绝大多数 python 代码
    |   ├── app # FASTapi 应用的代码
    |   ├── graph_executor # 图执行器，见其README
    |   ├── llm # 对LLM服务调用的包装
    |   ├── load_balance # 负载均衡模块，用于防止机器学习模型的服务触发限流
    |   ├── logger.py # 日志模块,使用logfire发送opentelemetry数据到日志追踪链路。
    |   ├── run.sh # 镜像入口文件
    |   ├── s3_FS # S3对象存储服务 python 接口
    |   ├── vector_db # 知识库（向量数据库）的抽象与实现。
    |   └── workflow # 图执行的定义，遵从无状态设计
    ├── docker # 容器配置文件和挂载目录
    ├── testcase # 单元测试
    ├── pip_resources # 构建镜像时的pip离线安装包
    ├── ... # 其他组件的配置文件，基本无代码。文件夹名为组件名。
    └── uv.lock 本项目使用 uv 进行依赖管理

IDIOT/api/
----------

``IDIOT/api/`` 目录下存放绝大多数逻辑代码，主要实现语言为python.

第一级目录的python包应为可独立验证的功能模块，可以拓展，但不建议更改已有的文件夹组织与命名。
