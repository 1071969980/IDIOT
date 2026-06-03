"""行级哈希计算工具。

使用 xxhash.xxh64 对单行内容计算哈希，取低 12 bit (3 nibbles) 映射到 NIBBLE_STR，
生成 3 字符的行锚点标识。用于 read_file 输出格式化和 edit_file 锚点验证。
"""

import xxhash

NIBBLE_STR = "ZPMQVRWSNKTXJBYH"  # 16 chars, 每个字符对应一个 nibble (0-15)
NIBBLE_CHARS = set(NIBBLE_STR)    # 合法哈希字符集合，用于校验


def compute_line_hash(line_content: str) -> str:
    """计算行的 3 字符哈希。

    算法: xxhash.xxh64(line_content) -> int -> 取低 12 bit (3 nibbles)
    -> 每个 nibble 作为索引映射到 NIBBLE_STR。
    """
    h = xxhash.xxh64(line_content.encode("utf-8")).intdigest()
    return (
        NIBBLE_STR[h & 0xF]
        + NIBBLE_STR[(h >> 4) & 0xF]
        + NIBBLE_STR[(h >> 8) & 0xF]
    )
