.. IDIOT documentation master file, created by
   sphinx-quickstart on Tue Aug  5 12:00:42 2025.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

IDIOT
=====

I.D.I.O.T.(Intelligent Development Integrated & Operations Toolkit)
--------------------------------------------------------------------
智能开发集成与运维工具包（下称IDIOT），是一个为了开发AI下游应用而组织的工具集成，主要语言为python。其遵照以下核心理念：

   1. 基于（流程）图的参数分发。为此我们提供一种新的代码组织风格，通过类型注解和装饰器将代码逻辑封装成有向无环图（DAG），并通过执行器执行。避免在开发与AI相关的业务流程时中出现巨大的“意大利面条”代码。
|

   2. Agent只是被看作普通的程序，只不过在流程（条件）控制和计算中涉及到深度学习相关计算。因此，我们避免对AI应用的开发思路做出任何代码层面的抽象。这方面我们推荐阅读HuggingFace的 `smalagents相关博客 <https://huggingface.co/blog/smolagents>`_。
|

   3. 在AI应用的持续优化中，基于“生命周期”的日志记录十分重要。于此，我们使用logfire,结合jaeger和prometheus, 通过opentelemetry协议，打造易用，高可用，可自定义的应用观测方案。该方案中logfire生命周期追踪可以跨越多线程与异步编程模型。多进程编程模型理论上也能支持。
|

   4. 上下文编排等同于低秩微调，是一般开发者更改模型行为的最佳方案。我们提供内存型和持久型向量数据库接口的最小示例，以及关系型数据库的成熟方案。并鼓励大家设计自己的知识库与上下文工程。
|

   5. 在复杂的AI应用中，常常涉及到大量模型服务的并发请求。因此，本工具箱提供了对于“均摊负载”的最小抽象，欢迎设计自己的负载均衡策略，以避免经常性的限流问题。
|

   6. 除提供工具的整合之外，我们并不对您应该开发什么应用或如何开发应用做出任何假设和建设性意见。如果您需要应用开发的示例，请参考项目列表。:doc:`Example Projects`
|


项目组件
-------
   1. 图执行器模块
   2. 负载均衡模块
   3. 日志模块
   4. 存储模块
       -  向量数据库
       -  关系型数据库
       -  对象存储
       -  图数据库（todo）
   5. 代码执行沙箱（todo）
   6. 人类交互 Human-in-the-loop 模块（todo）
   7. 示例项目（working）


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   User Guide
   Components
   Project Structure
   Example Projects