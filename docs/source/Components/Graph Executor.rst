Graph Executor
===============

Graph Executor 是一个用于提供一种特别的代码组织方式‘可选项’的组件。你可以使用phython的装饰器和类型注解功能，方便地将代码组织为以节点为单位的有向无环图。

这个组件设计遵循如下的理念。

* 每一个图定义应该是静态的（与类型定义同时）。
* 多次执行之间是无状态。
* 区分“连接”，“拉取”，“执行顺序（依赖）”的概念。

如何在图上定义节点
-------------------

在图上定义节点需要使用 ``@Graph`` 装饰器和 ``@dataclass`` 装饰器。节点必须是一个 dataclass 类，并且需要用 ``@Graph`` 装饰器注册到特定的图中。

以下是一个节点定义的示例：

.. code-block:: python

   from api.graph_executor.graph import Graph
   from dataclasses import dataclass

   @Graph("example")  # 将节点注册到名为"example"的图中
   @dataclass         # 节点必须是dataclass
   class NodeA:
       value: int = 0
       
       async def run(self):
           # 处理逻辑
           self.value += 10

关键要素说明：

1. **@Graph 装饰器**：用于将节点类注册到指定名称的图中，如 ``@Graph("test")`` 将节点注册到名为 "test" 的图中。

2. **@dataclass 装饰器**：每个节点必须是 dataclass 类型，用于定义节点的属性。

3. **run 方法**：定义节点的执行逻辑，必须包含命名为 ``run`` 的异步方法。该方法的返回值类型注解定义了节点的后继节点。

.. hint::
   
   Graph 是一个装饰器工厂，它创建一个 GraphMgr 实例，可以用来注册图节点。Graph 装饰器有两种使用方式：

   1. 直接使用模块级的 Graph 实例（推荐）：

   .. code-block:: python

      from api.graph_executor.graph import Graph

      @Graph("my_graph")
      @dataclass
      class MyNode:
          # 节点定义

   2. 自定义实例化装饰器：

   .. code-block:: python

      from api.graph_executor.graph import GraphMgr

      # 创建自己的 Graph 实例
      my_graph = GraphMgr()

      @my_graph("my_graph")
      @dataclass
      class MyNode:
          # 节点定义

   这种方式允许用户创建多个独立的图管理器实例，每个实例维护自己独立的图集合。

如何在节点之间定义连接
-------------------

节点之间的连接通过在 [run] 方法中定义类型注解来实现。节点连接主要有两种方式：

1. **通过返回值类型注解定义后继节点（连接）**：
   在 ``run`` 方法中使用返回值类型注解来声明当前节点的后继节点类型。

   .. code-block:: python

      @Graph("example")
      @dataclass
      class NodeA:
          value: int = 0
          
          async def run(self) -> "NodeB":
              # 声明NodeA的后继节点为NodeB
              self.value += 10
              return NodeB(self.value)

      @Graph("example")
      @dataclass
      class NodeB:
          value: int
          
          async def run(self) -> None:
              print(f"NodeB received value: {self.value}")

   在这个例子中，``-> "NodeB"`` 表示节点NodeA的后继节点是NodeB。

2. **通过参数声明拉取依赖**：
   后继节点可以通过在 ``run`` 方法中声明参数来"拉取"前驱节点的数据：

   .. code-block:: python

      @Graph("example")
      @dataclass
      class NodeB:
          value: int
          
          # 通过参数声明拉取NodeA的数据
          async def run(self, node_a: NodeA) -> None:
              print(f"NodeB received value: {self.value} from NodeA")
              print(f"NodeA's value is: {node_a.value}")

   在这个例子中，参数 ``node_a: NodeA`` 表示节点NodeB需要从节点NodeA拉取执行后的数据。


.. _Graph-Executor-Connection-definition:
.. _Graph-Executor-Pull-definition:
.. _Graph-Executor-Execution-Order-definition:
关键概念说明：

- **连接(Connection)**：通过返回值类型注解定义的节点间关系
- **拉取(Pull)**：后继节点通过参数声明从前驱节点获取数据
- **执行顺序(Execution Order)**：由类型注解驱动的连接和拉取都会构建依赖关系以影响执行顺序。执行顺序通过在有向无环图上执行拓扑排序得到。

节点之间的参数传递
---------------------

节点之间的参数传递有两种主要方式：通过函数返回值传递参数和通过拉取已执行节点的实例。

1. **通过函数返回值传递参数**：
   节点可以通过 ``run`` 方法的返回值将参数传递给后继节点。有两种方式实现：

   .. code-block:: python

      @Graph("example")
      @dataclass
      class NodeA:
          value: int = 0
          message: str = ""
          
          async def run(self) -> tuple["NodeB", "NodeC"]:
              # 方式1：直接返回后继节点实例
              # 后继节点会接收到对应的参数（基于字段匹配）
              self.value += 10
              self.message += "Processed by A"
              return NodeB(self.value, self.message), NodeC(self.value, self.message)
              
              # 方式2：返回字典指定传递给不同后继节点的参数
              # return {
              #     NodeB: {"value": self.value},  # NodeB只接收value参数
              #     NodeC: {"message": self.message}  # NodeC只接收message参数
              # }

      @Graph("example")
      @dataclass
      class NodeB:
          value: int 
          message: str | None
          
          async def run(self) -> None:
              print(f"NodeB received: value={self.value}, message={self.message}")

      @Graph("example")
      @dataclass
      class NodeC:
          value: int | None
          message: str
          
          async def run(self) -> None:
              print(f"NodeC received: value={self.value}, message={self.message}")

2. **通过拉取已执行的节点实例**：
   后继节点可以在 ``run`` 方法中声明参数来拉取前驱节点执行后的实例数据：

   .. code-block:: python

      @Graph("example")
      @dataclass
      class NodeB:
          value: int
          message: str
          
          # 通过在参数中声明 node_a: NodeA 来拉取NodeA执行后的实例
          async def run(self, node_a: NodeA) -> None:
              # 可以直接访问NodeA实例的所有公共属性
              print(f"NodeB received value: {self.value}")
              print(f"NodeA's final value: {node_a.value}")
              print(f"NodeA's message: {node_a.message}")


3. **多个来源的参数**：
   当一个节点被多个前驱节点推送数据时时，使用 ``ParamsList`` 和 ``ParamsLineageDict`` 来处理多个来源的数据，否则会在运行时抛出异常：

   .. code-block:: python

      from api.graph_executor.graph_core import ParamsLineageDict, ParamsList

      @Graph("example")
      @dataclass
      class NodeC:
          # 使用ParamsList接收多个来源的参数
          values: ParamsList[int]
          # 使用ParamsLineageDict接收来自不同来源的参数，其键为来源节点的类型名，
          messages: ParamsLineageDict[str]
          
          async def run(self) -> None:
              total = sum(self.values)  # 计算所有来源的value值之和
              combined_message = " | ".join(self.messages.values())  # 合并所有来源的消息
              print(f"NodeC total: {total}")
              print(f"NodeC combined message: {combined_message}")

节点的跳过
----------

在图执行过程中，某些情况下需要跳过特定节点的执行。Graph Executor 提供了手动和自动两种跳过机制。

1. **如何跳过节点**：
   节点可以通过返回 ``BypassSignal`` 对象来 **尝试** 跳过指定节点的执行：

   .. code-block:: python

      # 假设节其他点图如下，其他节点没有发送跳过信号
      # A --> B,C
      # B --> C,D
      # C --> E
      # D --> E

      from api.graph_executor.graph_core import BypassSignal

      @Graph("test")
      @dataclass
      class B:
          f_num: int | None
          f_msg: str | None
          
          async def run(self, a_node: A) -> tuple["C", "D"]:
              if self.f_num >= 200:
                  # BypassSignal 
                  return BypassSignal(C), BypassSignal(D)

   在这个例子中，当条件满足时 ``（f_num >= 200）`` ，B发送对节点D和节点C的跳过信号。
   因为节点D所有 **连接**的前继节点都向其发送了跳过信号，节点 D 将被跳过，不会执行其 ``run`` 方法。
   并且节点D将自动向其后继节点发送跳过信号（此处为节点E）。

    .. important::
        当且仅当所有 :ref:`连接<Graph-Executor-Connection-definition>` 的前继节点都向它发送了跳过信号时，节点才会被跳过。
        :ref:`拉取<Graph-Executor-Pull-definition>` 不是 :ref:`连接<Graph-Executor-Connection-definition>`
    
    .. hint::
        在如上的例子中，节点D被跳过，节点E不会被跳过，因为节点E的 **连接** 前继节点为节点D和节点C，而只有节点D向节点E发送了跳过信号。

2. **自动跳过机制**：
    当节点被跳过时，节点会向其所有后继节点发送跳过信号。
    根据上文规则， ::

        当且仅当所有连接的前继节点都向它发送了跳过信号时，节点才会被跳过。
    
    所以下游节点也有可能被自动跳过。

如何运行图和访问运行结果
---------------------

要运行一个图，需要使用 ``Graph.start`` 方法，并传入图名称和初始节点实例：

.. code-block:: python

   # 创建初始节点实例
   initial_node = NodeA(value=10, message="Start")

   # 运行图并获取结果
   nodes, params = asyncio.run(Graph.start("example", initial_node))

   # 访问特定节点的执行结果
   node_a_result = nodes.get("EndNode")
   if node_a_result:
       print(f"NodeA value: {node_a_result.value}")

``Graph.start`` 方法返回两个字典：

1. **nodes**: 包含所有已执行节点实例的字典，键为节点类名，值为节点实例
2. **params**: 包含节点间传递参数时的内部参数池

.. hint::
   
   可以通过访问 nodes 字典中的节点实例来获取执行后的节点状态和属性值。

.. hint::
    ``Graph.start`` 方法的第二个参数等同与

关于日志记录
-----------

每次执行图，和节点执行时，都会通过logfire创建生命周期（logfire.span）日志。在节点的``run``方法中，建议通过logire的相关方法来记录日志，以达到最好的可观测性。

更多请详见 :doc:`Logger System`

关于图的可视化
------------

使用 ``Graph.render_as_mermaid`` 方法可以返回mermaid图表