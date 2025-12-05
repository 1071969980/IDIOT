# 声明新的FastAPI接口设计规范

本文档定义了IDIOT项目中FastAPI接口的设计规范和最佳实践。

## 1. 项目结构

### 1.1 路由组织结构

```
api/app/
├── 模块名/
│   ├── router_declare.py    # 路由声明文件
│   ├── data_model.py       # 数据模型定义
│   └── endpoints.py        # 具体接口实现
└── main.py                 # 应用入口和路由注册
```

### 1.2 文件职责

- **router_declare.py**: 定义APIRouter实例，配置路由前缀和标签
- **data_model.py**: 定义请求/响应的Pydantic模型
- **endpoints.py**: 实现具体的接口逻辑

## 2. 路由声明规范

### 2.1 路由声明文件

每个功能模块必须创建独立的 `router_declare.py` 文件：

```python
from fastapi import APIRouter

router = APIRouter(
    prefix="/模块名",
    tags=["模块标签"],
)
```

**要求**：
- 使用 `prefix` 定义路由前缀，格式为 `/{module_name}`
- 使用 `tags` 为路由分组，便于API文档组织
- router对象命名统一为 `router`

## 3. Pydantic模型规范

### 3.1 模型定义

所有请求和响应模型必须继承自 `BaseModel`：

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class RequestModel(BaseModel):
    """请求模型描述"""
    required_field: str = Field(..., description="必填字段描述")
    optional_field: Optional[str] = Field(None, description="可选字段描述")
    enum_field: Literal["option1", "option2"] = Field(..., description="枚举字段")

class ResponseModel(BaseModel):
    """响应模型描述"""
    id: UUID
    created_at: datetime
    updated_at: datetime
```

### 3.2 字段定义规范

- **必填字段**: 使用 `Field(..., description="描述")`
- **可选字段**: 使用 `Optional[Type] = Field(None, description="描述")` 或 `Type = Field(default="默认值")`
- **枚举字段**: 使用 `Literal["option1", "option2"]` 限制值范围
- **特殊类型**:
  - 使用 `UUID` 处理唯一标识符
  - 使用 `datetime` 处理时间戳
  - 使用 `bool` 处理布尔值

## 4. 接口实现规范

### 4.1 基本接口结构

```python
@router.http_method("/endpoint", response_model=ResponseModel)
async def endpoint_name(
    request_param: Annotated[RequestModel, Body()],
    query_param: Annotated[str, Query()],
    user: Annotated[_User, Depends(get_current_active_user)]
) -> ResponseModel:
    """接口功能描述"""
    # 实现逻辑
    return response_data
```

### 4.2 参数类型注解

- **请求体**: `Annotated[RequestModel, Body()]`
- **查询参数**: `Annotated[Type, Query()]`
- **路径参数**: `param: Type` (直接定义)
- **依赖注入**: `Annotated[Type, Depends()]`

### 4.3 认证相关接口

**用户认证**：
```python
@router.post("/protected_endpoint")
async def protected_api(
    user: Annotated[_User, Depends(get_current_active_user)]
) -> dict:
    """需要认证的接口"""
    return {"user_id": user.id}
```

**仅获取用户ID**：
```python
@router.get("/endpoint")
async def endpoint(
    user_id: Annotated[UUID, Depends(get_current_user_id)]
) -> dict:
    """仅需用户ID的接口"""
    return {"user_id": user_id}
```

## 5. 错误处理规范

### 5.1 异常处理模式

```python
@router.post("/endpoint")
async def endpoint(
    request: Annotated[RequestModel, Body()],
    user: Annotated[_User, Depends(get_current_active_user)]
) -> ResponseModel:
    """接口功能描述"""
    try:
        # 业务逻辑
        return response_data

    except SpecificException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"具体错误信息: {e!s}",
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器内部错误: {e!s}",
        ) from e
```

## 6. 导入规范

### 6.1 导入顺序

```python
# 标准库导入
from typing import Annotated, Optional, Literal
from uuid import UUID
from datetime import datetime

# 第三方库导入
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

# 项目内部导入
from api.authentication.utils import get_current_active_user
from api.authentication.sql_stat.utils import _User

from .router_declare import router
from .data_model import RequestModel, ResponseModel
```

遵循以上规范可以确保接口的一致性、可维护性和安全性。