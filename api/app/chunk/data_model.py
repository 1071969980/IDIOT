from pydantic import BaseModel
from enum import Enum

class SplitType(str, Enum):
    separator: str = "separator"
    regex: str = "regex"
    sentence: str = "sentence"
    markdown_block: str = "markdown_block"
    kamradt_chunk: str = "kamradt_chunk" # 分句->嵌入->启发式聚类
    

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

class KamradtChunkConfig(BaseModel):
    sentence_window: int = 5 # 句子窗口,一个句子的嵌入值生成自包含自身的前文窗口
    sentence_window_offset: int = 0
    except_chunk_size: int = 200

class LengthLimitConfig(BaseModel):
    min_length: int = -1
    max_length: int = -1
    turncate_level: TruncateLevel
    
class SplitConfig(BaseModel):
    type: SplitType
    config: SeparatorConfig | RegexConfig | KamradtChunkConfig | None
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