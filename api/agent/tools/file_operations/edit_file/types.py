"""edit_file 工具的类型定义。

包含编辑操作枚举、锚点引用模型、统一编辑动作、锚点输出模型和锚点解析函数。
"""

import re
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict

from ..line_hash import NIBBLE_CHARS


class EditOp(str, Enum):
    REPLACE = "replace"
    APPEND = "append"
    PREPEND = "prepend"
    REPLACE_TEXT = "replace_text"


@dataclass(frozen=True)
class AnchorRef:
    """解析后的锚点引用，如 '5#MQP'。"""

    line: int   # 1-based 行号
    hash: str   # 3 字符哈希


class AnchorParseError(ValueError):
    """锚点格式错误。"""


_ANCHOR_RE = re.compile(r"^(\d+)#([A-Z]{3})$")


def parse_anchor_ref(ref: str) -> AnchorRef:
    """解析锚点引用字符串。

    Args:
        ref: 格式为 '<line>#<hash>'，如 '5#MQP'

    Returns:
        AnchorRef(line=5, hash='MQP')

    Raises:
        AnchorParseError: 格式错误、行号 < 1、或哈希字符不在 NIBBLE_STR 中
    """
    m = _ANCHOR_RE.match(ref)
    if not m:
        raise AnchorParseError(
            f"锚点格式错误: '{ref}'，期望格式为 '<行号>#<3字符哈希>'，如 '5#MQP'"
        )
    line = int(m.group(1))
    hash_str = m.group(2)

    if line < 1:
        raise AnchorParseError(f"行号必须 >= 1，当前: {line}")

    invalid_chars = [c for c in hash_str if c not in NIBBLE_CHARS]
    if invalid_chars:
        raise AnchorParseError(
            f"哈希字符 '{hash_str}' 包含非法字符 {invalid_chars}，"
            f"合法字符为: {''.join(sorted(NIBBLE_CHARS))}"
        )

    return AnchorRef(line=line, hash=hash_str)


class EditAction(BaseModel):
    """统一的编辑动作。

    由工具层 (步骤 1) 构建，传递给存储后端的 edit_file_v2。
    """

    model_config = ConfigDict(extra='allow')

    op: EditOp
    # replace: start_line/end_line 为 1-based, end_line inclusive
    # append/prepend: start_line 为锚点行号
    start_line: int | None = None
    end_line: int | None = None
    # 替换/插入的新行内容 (纯文本，无 LINE#HASH: 前缀)
    new_lines: list[str] = []
    # replace_text only
    old_text: str | None = None
    new_text: str | None = None
    replace_all: bool = False
    # 锚点哈希 (由工具层解析锚点引用后填入，供存储后端验证)
    pos_hash: str | None = None
    end_hash: str | None = None


class EditAnchorOutput(BaseModel):
    """编辑锚点输出，用于构建 Edit Anchors 响应块。"""

    start_line: int            # 变更首行 (1-based)
    end_line: int              # 变更末行 (1-based)
    formatted_lines: list[str]  # hash-line 格式化行列表
    total_affected: int        # 受影响行数
