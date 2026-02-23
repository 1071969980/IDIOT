"""
LLM 数据类型模块 - 参考 OpenAI API

本模块提供两类数据结构：
1. TypedDict 版本：用于传入网络调用函数（发送给 LLM API）
2. BaseModel 版本：用于网络调用结果解析后，在程序逻辑内使用
"""

# ==================== Chat Messages ====================
from .chat_messages import (
    # TypedDict 版本
    ChatCompletionUserMessageParamDict,
    ChatCompletionAssistantMessageParamDict,
    ChatCompletionSystemMessageParamDict,
    ChatCompletionToolMessageParamDict,
    ChatCompletionMessageParamDict,
    # BaseModel 版本
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionMessageParam,
)

# ==================== Functions ====================
from .functions import (
    # TypedDict 版本
    FunctionDefinitionDict,
    FunctionCallDict,
    # BaseModel 版本
    FunctionDefinition,
    FunctionCall,
)

# ==================== Tool Calls ====================
from .tool_calls import (
    # TypedDict 版本
    ChatCompletionToolParamDict,
    ChatCompletionMessageToolCallDict,
    # BaseModel 版本
    ChatCompletionToolParam,
    ChatCompletionMessageToolCall,
)

# ==================== Usage ====================
from .usage import (
    # TypedDict 版本
    CompletionUsageDict,
    # BaseModel 版本
    CompletionUsage,
)

# ==================== Chat Completion ====================
from .chat_completion import (
    # TypedDict 版本
    MessageDict,
    ChatCompletionChoiceDict,
    ChatCompletionDict,
    # BaseModel 版本
    Message,
    ChatCompletionChoice,
    ChatCompletion,
)

# ==================== Chat Completion Chunk ====================
from .chat_completion_chunk import (
    # TypedDict 版本
    ChoiceDeltaToolCallFunctionDict,
    ChoiceDeltaToolCallDict,
    ChoiceDeltaDict,
    ChatCompletionChunkChoiceDict,
    ChatCompletionChunkDict,
    # BaseModel 版本
    ChoiceDeltaToolCallFunction,
    ChoiceDeltaToolCall,
    ChoiceDelta,
    ChatCompletionChunkChoice,
    ChatCompletionChunk,
)

# ==================== Embedding ====================
from .embedding import (
    # TypedDict 版本
    EmbeddingDict,
    CreateEmbeddingResponseDict,
    # BaseModel 版本
    Embedding,
    CreateEmbeddingResponse,
)

# ==================== Async Stream ====================
from .async_stream import (
    AsyncStream,
)

__all__ = [
    # Chat Messages
    "ChatCompletionUserMessageParamDict",
    "ChatCompletionAssistantMessageParamDict",
    "ChatCompletionSystemMessageParamDict",
    "ChatCompletionToolMessageParamDict",
    "ChatCompletionMessageParamDict",
    "ChatCompletionUserMessageParam",
    "ChatCompletionAssistantMessageParam",
    "ChatCompletionSystemMessageParam",
    "ChatCompletionToolMessageParam",
    "ChatCompletionMessageParam",
    # Functions
    "FunctionDefinitionDict",
    "FunctionCallDict",
    "FunctionDefinition",
    "FunctionCall",
    # Tool Calls
    "ChatCompletionToolParamDict",
    "ChatCompletionMessageToolCallDict",
    "ChatCompletionToolParam",
    "ChatCompletionMessageToolCall",
    # Usage
    "CompletionUsageDict",
    "CompletionUsage",
    # Chat Completion
    "MessageDict",
    "ChatCompletionChoiceDict",
    "ChatCompletionDict",
    "Message",
    "ChatCompletionChoice",
    "ChatCompletion",
    # Chat Completion Chunk
    "ChoiceDeltaToolCallFunctionDict",
    "ChoiceDeltaToolCallDict",
    "ChoiceDeltaDict",
    "ChatCompletionChunkChoiceDict",
    "ChatCompletionChunkDict",
    "ChoiceDeltaToolCallFunction",
    "ChoiceDeltaToolCall",
    "ChoiceDelta",
    "ChatCompletionChunkChoice",
    "ChatCompletionChunk",
    # Embedding
    "EmbeddingDict",
    "CreateEmbeddingResponseDict",
    "Embedding",
    "CreateEmbeddingResponse",
    # Async Stream
    "AsyncStream",
]
