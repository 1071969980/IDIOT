"""
角色对话策略更新功能 - 数据模型和常量定义

本模块定义了：
1. Agent 工具的参数模型（Pydantic BaseModel）
2. 外部容器的类型（TypedDict，用于闭包捕获变量）
3. 常量定义（如最大循环次数、超时时间、审查分数阈值等）

设计文档参考：
- docs/dev_spec/agent_role_conversation_strategies_background_update_task_spec_docs/
"""

from pydantic import BaseModel, Field
from typing import TypedDict


# ========== 工具参数模型 ==========

class ReadStrategiesPartToolParam(BaseModel):
    """Agent A 的工具参数：读取对话策略的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")


class EditStrategiesToolParam(BaseModel):
    """Agent A 的工具参数：编辑对话策略内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现（默认只替换第一个）")


class ReadGuidancePartToolParam(BaseModel):
    """Agent B 的工具参数：读取对话总结指导的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")


class EditGuidanceToolParam(BaseModel):
    """Agent B 的工具参数：编辑对话总结指导内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现")


class SubmitReviewToolParam(BaseModel):
    """Agent C 的工具参数：提交审查结果"""
    score: int = Field(..., ge=0, le=100, description="审查分数（0-100）")
    suggestions: str = Field(default="", description="修改建议（如果评分低于 80 分）")


# ========== 外部容器类型定义（闭包捕获变量） ==========

class AgentAResult(TypedDict):
    """
    Agent A 的外部容器类型（由工具闭包捕获并修改）

    Agent 函数本身不返回任何值（返回类型为 None），执行结果通过工具回调函数写入这些外部容器。
    """
    updated_strategies: str  # 工具回调函数写入更新后的策略
    tool_called: bool  # 工具回调函数标记是否调用了工具


class AgentBResult(TypedDict):
    """
    Agent B 的外部容器类型（由工具闭包捕获并修改）

    Agent 函数本身不返回任何值（返回类型为 None），执行结果通过工具回调函数写入这些外部容器。
    """
    updated_guidance: str  # 工具回调函数写入更新后的指导
    tool_called: bool  # 工具回调函数标记是否调用了工具


class AgentCResult(TypedDict):
    """
    Agent C 的外部容器类型（由工具闭包捕获并修改）

    Agent 函数本身不返回任何值（返回类型为 None），执行结果通过工具回调函数写入这些外部容器。
    """
    score: int  # 工具回调函数写入审查分数
    suggestions: str  # 工具回调函数写入修改建议


# ========== 常量定义 ==========

# 工具调用最大重试次数
MAX_TOOL_CALL_RETRIES = 3

# 审查循环最大次数
MAX_REVIEW_LOOPS = 3

# 审查通过分数阈值
REVIEW_PASS_THRESHOLD = 80

# 第一阶段超时时间（秒）
PHASE1_TIMEOUT = 30

# 第三阶段分布式锁超时时间（秒）
PHASE3_LOCK_TIMEOUT = 300
