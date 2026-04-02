# 添加新的 LLM 提供商

本文档介绍如何在 IDIOT 系统中添加新的 LLM 提供商支持。

## 概述

IDIOT 系统的负载均衡器支持多个 LLM 提供商的统一接入。添加新的 LLM 提供商涉及 4 个文件的修改，以最近的智谱（ZhiPu）接入为例：

| # | 文件 | 作用 |
|---|------|------|
| 1 | `api/core/env_config.py` | 在 `LLMServiceConfig` 中添加 API Key 等环境变量 |
| 2 | `api/llm/<provider>.py` | 创建 `async_client()` 工厂函数，用 `lru_cache` 缓存 `AsyncOpenAI` 实例 |
| 3 | `api/load_balance/constant.py` | 定义服务名称常量并加入 `__all__` |
| 4 | `api/load_balance/init/<provider>_service.py` | 注册函数，创建实例并注册到负载均衡器 |

此外还需更新 `api/load_balance/init/__init__.py` 和 `k8s/base/01-secrets.yaml`。

## 实现步骤

### 1. 添加环境变量配置

打开 `api/core/env_config.py`，在 `LLMServiceConfig` 类中添加配置。

**必填字段（延迟加载）**：使用 `{name}_value` 内部字段 + `@property` 延迟加载，仅在访问时检查环境变量是否存在。

```python
class LLMServiceConfig(BaseSettings):
    # ... 现有字段 ...

    # 内部字段存储环境变量值（可选，默认 None）
    zhipu_api_key_value: Optional[SecretStr] = Field(default=None, alias="ZHIPU_API_KEY")

    @property
    def zhipu_api_key(self) -> SecretStr:
        """智谱 API Key"""
        if self.zhipu_api_key_value is None:
            raise ValueError("ZHIPU_API_KEY is not set")
        return self.zhipu_api_key_value
```

**可选字段（有默认值）**：直接使用 `Field(default=...)` 指定默认值。

```python
    zhipu_timeout: int = Field(default=30, alias="ZHIPU_TIMEOUT")
```

**配置说明**：

| 字段类型 | 实现方式 | 说明 |
|----------|----------|------|
| 必填字段 | `{name}_value` + `@property` | 延迟加载，仅在访问时检查环境变量是否存在 |
| 可选字段 | `Field(default=...)` | 直接指定默认值，实例化时即可使用 |
| 敏感字段 | `SecretStr` 类型 | 日志打印时自动隐藏，需通过 `.get_secret_value()` 获取明文 |

### 2. 创建客户端工厂函数

在 `api/llm/` 下创建 `<provider>.py`，实现带 `lru_cache` 的 `async_client()` 函数：

```python
# api/llm/zhipu.py
from functools import lru_cache

from openai import AsyncOpenAI

from api.core.env_config import llm_service_config


@lru_cache(maxsize=1)
def async_client() -> AsyncOpenAI:
    key = llm_service_config.zhipu_api_key.get_secret_value()
    return AsyncOpenAI(
        api_key=key,
        base_url="https://open.bigmodel.cn/api/paas/v4/",
    )
```

> `lru_cache(maxsize=1)` 确保全局只创建一个客户端实例。`base_url` 硬编码在工厂函数中，因为每个提供商的地址固定。

### 3. 添加服务名常量

在 `api/load_balance/constant.py` 中添加服务名称常量并加入 `__all__` 导出列表：

```python
# 常量定义
GLM_5_SERVICE_NAME = "glm-5"
GLM_4_7_SERVICE_NAME = "glm-4.7"

# __all__ 中添加
__all__ = [
    # ... 现有条目 ...
    "GLM_5_SERVICE_NAME",
    "GLM_4_7_SERVICE_NAME",
]
```

### 4. 创建服务注册文件

在 `api/load_balance/init/` 下创建 `<provider>_service.py`。每个模型对应一个注册函数：

```python
# api/load_balance/init/zhipu_service.py
from api.llm.zhipu import async_client as zhipu_async_client

from ..constant import (
    GLM_5_SERVICE_NAME,
    GLM_4_7_SERVICE_NAME,
    LOAD_BLANCER,
)
from ..service_instance import AsyncOpenAIServiceInstance


def register_glm_5_service() -> None:
    service_reg = LOAD_BLANCER.registry
    zhipu_instance = AsyncOpenAIServiceInstance(
        name="zhipu",
        openai_client=zhipu_async_client(),
        model="glm-5",
    )
    service_reg.register_service(GLM_5_SERVICE_NAME, zhipu_instance)


def register_glm_4_7_service() -> None:
    service_reg = LOAD_BLANCER.registry
    zhipu_instance = AsyncOpenAIServiceInstance(
        name="zhipu",
        openai_client=zhipu_async_client(),
        model="glm-4.7",
    )
    service_reg.register_service(GLM_4_7_SERVICE_NAME, zhipu_instance)
```

关键点：
- 使用 `AsyncOpenAIServiceInstance` 包装 `AsyncOpenAI` 客户端和模型名
- `name` 参数标识提供商（非模型），同一提供商的不同模型共享相同的 `name`
- 通过 `LOAD_BLANCER.registry.register_service()` 注册

### 5. 启用注册

编辑 `api/load_balance/init/__init__.py`，导入注册函数并调用：

```python
from .zhipu_service import (register_glm_5_service,
                            register_glm_4_7_service)

# 在模块级别调用，导入时自动注册
register_glm_5_service()
register_glm_4_7_service()
```

> 暂时不启用的服务可以注释掉调用行。

### 6. 更新部署配置

在 `k8s/base/01-secrets.yaml` 的 `idiot-secrets` 中添加新的 API Key：

```yaml
stringData:
  # ... 现有条目 ...
  ZHIPU_API_KEY: ""
```

本地开发时在 `.env` 文件中设置：

```bash
ZHIPU_API_KEY=your_api_key_here
```

## 示例参考

可以参考现有的实现：
- `api/llm/deepseek.py` + `api/load_balance/init/deepseek_service.py` — DeepSeek 服务
- `api/llm/tongyi.py` + `api/load_balance/init/qwen_commercial_service.py` — 通义千问服务（多个模型共享同一客户端）
- `api/llm/zhipu.py` + `api/load_balance/init/zhipu_service.py` — 智谱 GLM 服务
