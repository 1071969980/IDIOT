# 添加新的 LLM 提供商

本文档介绍如何在 IDIOT 系统中添加新的 LLM 提供商支持。

## 概述

IDIOT 系统的负载均衡器支持多个 LLM 提供商的统一接入。添加新的 LLM 提供商需要实现服务实例类并配置相应的负载均衡策略。

## 实现步骤

### 1. 创建服务实例类

在 `api/load_balance/` 中创建新的服务实例类，继承 `ServiceInstanceBase`：

```python
from api.load_balance.service_instance_base import ServiceInstanceBase
from openai import AsyncOpenAI

class NewLLMServiceInstance(ServiceInstanceBase):
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )

    async def generate(self, messages: List[Dict], **kwargs):
        """实现 LLM 生成接口"""
        return await self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            **kwargs
        )
```

### 2. 实现接口要求

根据 LLM 提供商的 API 特性，实现以下接口之一：

- **AsyncOpenAI 兼容接口**：如果提供商支持 OpenAI 兼容的 API 格式
- **自定义委托函数**：如果提供商有特殊的 API 格式，需要实现委托函数

### 3. 注册服务到负载均衡器

在 `LOAD_BLANCER` 中注册新服务：

```python
from api.load_balance.load_balancer import LOAD_BALANCER

# 注册新服务
LOAD_BALANCER.register_service(
    service_name="new_llm",
    service_class=NewLLMServiceInstance,
    retry_config={
        "max_retries": 3,
        "backoff_factor": 2.0
    }
)
```

### 4. 配置重试策略

为新的 LLM 服务配置适当的重试策略：

```python
from api.load_balance.retry import RetryStrategy

retry_strategy = RetryStrategy(
    max_retries=3,
    backoff_factor=2.0,
    retry_on_status=[429, 500, 502, 503, 504]
)
```

### 5. 更新部署配置

根据部署方式，添加新的环境变量配置：

**Docker Compose**：

```yaml
# docker-compose.yml
services:
  idiot-api:
    environment:
      - NEW_LLM_API_KEY=${NEW_LLM_API_KEY}
      - NEW_LLM_BASE_URL=${NEW_LLM_BASE_URL}
```

**Kubernetes**：

```yaml
# k8s/configmap.yaml 或 k8s/secrets.yaml
env:
  - name: NEW_LLM_API_KEY
    valueFrom:
      secretKeyRef:
        name: llm-secrets
        key: new-llm-api-key
  - name: NEW_LLM_BASE_URL
    value: "https://api.newllm.com/v1"
```

### 6. 添加环境变量配置

IDIOT 使用 pydantic-settings 集中管理环境变量。所有环境变量配置位于 `api/core/env_config.py`。

#### 6.1 在 `LLMServiceConfig` 中添加配置

打开 `api/core/env_config.py`，在 `LLMServiceConfig` 类中添加新配置：

**必填字段（延迟加载）**：

```python
class LLMServiceConfig(BaseSettings):
    # ... 现有字段 ...

    # 新增必填字段 - 使用内部字段存储 + @property 延迟加载
    new_llm_api_key_value: Optional[SecretStr] = Field(default=None, alias="NEW_LLM_API_KEY")
    new_llm_base_url_value: Optional[str] = Field(default=None, alias="NEW_LLM_BASE_URL")

    @property
    def new_llm_api_key(self) -> SecretStr:
        """新 LLM 提供商 API Key"""
        if self.new_llm_api_key_value is None:
            raise ValueError("NEW_LLM_API_KEY is not set")
        return self.new_llm_api_key_value

    @property
    def new_llm_base_url(self) -> str:
        """新 LLM 提供商 Base URL"""
        if self.new_llm_base_url_value is None:
            raise ValueError("NEW_LLM_BASE_URL is not set")
        return self.new_llm_base_url_value
```

**可选字段（有默认值）**：

```python
class LLMServiceConfig(BaseSettings):
    # ... 现有字段 ...

    # 新增可选字段 - 直接使用 Field 指定默认值
    new_llm_timeout: int = Field(default=30, alias="NEW_LLM_TIMEOUT")
```

#### 6.2 在服务实例中使用配置

```python
from api.core.env_config import llm_service_config

class NewLLMServiceInstance(ServiceInstanceBase):
    def __init__(self, config: ServiceConfig):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=llm_service_config.new_llm_api_key.get_secret_value(),
            base_url=llm_service_config.new_llm_base_url
        )
```

#### 6.3 配置说明

| 字段类型 | 实现方式 | 说明 |
|----------|----------|------|
| 必填字段 | `{name}_value` + `@property` | 延迟加载，仅在访问时检查环境变量是否存在 |
| 可选字段 | `Field(default=...)` | 直接指定默认值，实例化时即可使用 |
| 敏感字段 | `SecretStr` 类型 | 日志打印时自动隐藏，需通过 `.get_secret_value()` 获取明文 |

#### 6.4 在 `.env` 文件中设置值

```bash
NEW_LLM_API_KEY=your_api_key_here
NEW_LLM_BASE_URL=https://api.newllm.com/v1
```

## 最佳实践

1. **错误处理**：实现适当的错误处理和日志记录
2. **监控集成**：添加 OpenTelemetry 追踪支持
3. **参数验证**：验证 API 参数的有效性
4. **限流处理**：实现适当的限流和退避策略
5. **健康检查**：实现服务健康检查机制
6. **环境变量管理**：
   - 所有环境变量必须在 `api/core/env_config.py` 中集中管理
   - API Key 等敏感信息使用 `SecretStr` 类型
   - 必填字段使用 `@property` 延迟加载，避免启动时立即报错
   - 使用 `Field(alias="ENV_VAR_NAME")` 映射环境变量名

## 示例参考

可以参考现有的实现：
- `api/load_balance/init/deepseek_service.py` - DeepSeek 服务实现
- `api/load_balance/init/tongyi_service.py` - Tongyi 服务实现

## 测试

为新的 LLM 提供商编写测试：

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_new_llm_service():
    # 测试服务初始化
    # 测试 API 调用
    # 测试错误处理
    pass
```

## 相关文档

- [负载均衡器详细文档](../source/Components/Load%20Blancer.rst)
- [重试策略配置](../source/Components/Load%20Blancer.rst#retry-strategies)
- [OpenTelemetry 集成](../source/Components/Logger%20System.rst)