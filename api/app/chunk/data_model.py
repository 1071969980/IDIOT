from pydantic import BaseModel
from enum import Enum

class SplitType(str, Enum):
    separator: str = "separator"
    regex: str = "regex"
    markdown_block: str = "markdown_block"
    kamradt_chunk: str = "kamradt_chunk" # 分句，嵌入，启发式聚类

class TruncateLevel(str, Enum):
    char: str = "char"
    sentence: str = "sentence"
    
class SeparatorConfig(BaseModel):
    separator: str
    keep_separator: bool
    keep_as_prefix: bool
    keep_as_suffix: bool

class RegexConfig(BaseModel):
    regex: str
    keep_regex_match: bool
    keep_as_prefix: bool
    keep_as_suffix: bool

class LengthLimitConfig(BaseModel):
    min_length: int = -1
    max_length: int = -1
    turncate_level: TruncateLevel
    
class SplitConfig(BaseModel):
    type: SplitType
    config: SeparatorConfig | RegexConfig | None
    length_limit: LengthLimitConfig

class HierarchicalChunkConfig(BaseModel):
    markdown_uuid: str
    parent_split_config: SplitConfig
    child_split_config: SplitConfig | None =  None

class HierarchicalChunk(BaseModel):
    parent: str
    children: list[str]
    
class HierarchicalChunkResponse(BaseModel):
    chunks: list[HierarchicalChunk]