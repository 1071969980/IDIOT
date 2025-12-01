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

### 5. 更新 Docker 配置

在 `docker-compose.yml` 中添加新服务所需的配置：

```yaml
services:
  idiot-api:
    environment:
      - NEW_LLM_API_KEY=${NEW_LLM_API_KEY}
      - NEW_LLM_BASE_URL=${NEW_LLM_BASE_URL}
```

### 6. 添加环境变量

在 `.env` 文件中添加所需的 API 密钥和配置：

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