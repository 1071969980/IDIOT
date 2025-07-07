# 负载均衡模块文档

## 模块概述
负载均衡模块为微服务架构提供智能路由决策。通过策略化设计支持多种负载均衡算法，结合服务注册中心实现动态实例管理。

## 核心组件
1. `LoadBalanceStrategy` - 抽象基类定义统一的策略接口
2. `RandomStrategy` - 随机选择实例的实现策略
3. `RoundRobinStrategy` - 轮询选择实例的实现策略
4. `LoadBalancer` - 核心控制器协调策略与注册中心
5. `ServiceRegistry` - 服务注册中心访问接口
6. `ServiceInstanceBase` - 服务实例的基础抽象类

## 使用示例
```python
# 初始化负载均衡器
from api.load_balance import LOAD_BALANCER, QWEN_MAX_SERVICE_NAME
from api.load_balance.delegate.openai import generation_delegate_for_async_openai

# 创建消息列表
messages = [...]
# 创建重试配置
retry_configs = ...
# 其他参数
kwargs = {...}

# 定义闭包
def delegate(instance):
    # other logic here
    return generation_delegate_for_async_openai(
        instance,
        messages,
        retry_configs
        **kwargs
    )

# 执行请求
result = await LOAD_BALANCER.execute(
    QWEN_MAX_SERVICE_NAME,
    delegate,
)
```

## 文件结构说明
- `__init__.py`: Python包初始化文件
- `constant.py`: 定义模块级常量和全局配置
- `exception.py`: 自定义异常类型定义
- `load_balance_strategy.py`: 负载均衡策略接口及基础实现
- `load_balancer.py`: 负载均衡核心控制器实现
- `service_instance.py`: 服务实例基础类和具体实现
- `service_regeistry.py`: 服务注册中心实现
- `delegate/`: 包含具体服务委托函数实现的目录
  - `openai.py`: OpenAI服务委托函数实现
- `init/`: 包含服务初始化实现的目录，导入该包自动完成服务初始化

# 扩展步骤
1. 定义新的服务名称常量
   在`constant.py`中定义新的服务名称常量，例如：
   ```python
   NEW_SERVICE_NAME = "new-service"
   ```

2. 创建新的服务初始化模块
   在`init/`目录下创建新的服务初始化实现文件，例如`new_service.py`。

3. 实现服务注册函数
   在新的服务初始化文件中实现服务注册函数，例如：
   ```python
   def register_new_service():
       # 实现服务注册逻辑
       pass
   ```

4. 添加模块导入和自动注册
   在`init/__init__.py`中添加新模块的导入和自动注册调用：
   ```python
   from .new_service import register_new_service
   register_new_service()
   ```
