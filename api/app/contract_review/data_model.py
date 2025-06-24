from pydantic import BaseModel
from ..chunk.data_model import HierarchicalChunk
from ..data_model import TaskStatus
from enum import Enum

class ReviewStance(str, Enum):
    PartyA = "PartyA"
    PartyB = "PartyB"
    Fair = "Fair"
    
class ReviewEntryImportance(str, Enum):
    High = "High"
    Medium = "Medium"
    Low = "Low"

class ReviewEntry(BaseModel):
    brief: str
    detail_rules: str
    importance: ReviewEntryImportance

class ReviewRisk(BaseModel):
    raw_text: str
    why_risk: str
    suggestion: str

class ReviewResult(BaseModel):
    entry: ReviewEntry
    risks: list[ReviewRisk]

class ReviewWorkflowResult(BaseModel):
    result: list[ReviewResult]

class ReviewRequest(BaseModel):
    chunks_overlap: int | None = 1
    # 实际执行任务的延时时间, 主要用于避免过多请求在同一时间点并发而导致频繁429错误。
    delay: float | None = 0
    stance: ReviewStance
    chunks: list[HierarchicalChunk]
    entries: list[ReviewEntry]
    
class ReviewResponse(BaseModel):
    stauts: TaskStatus
    task_id: str
    result: list[ReviewResult] | None

class SuggestionMergeRequest(BaseModel):
    risks: list[ReviewRisk]
    
class SuggestionMergeResponse(BaseModel):
    stauts: TaskStatus
    task_id: str
    result: list[ReviewRisk] | None
