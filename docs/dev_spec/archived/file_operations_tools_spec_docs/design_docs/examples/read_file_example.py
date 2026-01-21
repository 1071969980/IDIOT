# read_file 工具使用示例

## 示例 1：读取整个文件

```python
# 调用
result = await read_file_tool(
    file_path="src/main.py"
)

# 返回
ToolTaskResult(
    str_content="""文件内容：src/main.py
读取行数：1-100 / 共100行

import sys
from pathlib import Path

def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""",
    occur_error=False
)
```

## 示例 2：读取部分内容（带行号）

```python
# 调用
result = await read_file_tool(
    file_path="src/utils.py",
    offset=10,
    limit=20,
    show_line_numbers=True
)

# 返回
ToolTaskResult(
    str_content="""文件内容：src/utils.py
读取行数：11-30 / 共150行

    11→def process_data(data):
    12→    """处理数据"""
    13→    result = []
    14→    for item in data:
    15→        processed = transform(item)
    16→        result.append(processed)
    17→    return result
    18→
    19→def transform(item):
    20→    """转换单个项目"""
    21→    return item.upper()
    22→
    23→class DataProcessor:
    24→    def __init__(self, config):
    25→        self.config = config
    26→        self.cache = {}
    27→
    28→    def process(self, data):
    29→        """处理数据"""
    30→        return process_data(data)
""",
    occur_error=False
)
```

## 示例 3：offset 超出文件范围

```python
# 调用
result = await read_file_tool(
    file_path="src/small.py",
    offset=100  # 文件只有 50 行
)

# 返回
ToolTaskResult(
    str_content="""文件内容：src/small.py
起始行超出文件范围（文件共50行，offset=100）
""",
    occur_error=False
)
```

## 示例 4：读取空文件

```python
# 调用
result = await read_file_tool(
    file_path="logs/empty.log"
)

# 返回
ToolTaskResult(
    str_content="""文件内容：logs/empty.log
文件为空
""",
    occur_error=False
)
```

## 示例 5：文件不存在

```python
# 调用
result = await read_file_tool(
    file_path="nonexistent.py"
)

# 返回
ToolTaskResult(
    str_content="""读取文件失败：文件不存在：nonexistent.py
""",
    occur_error=True
)
```

## 示例 6：读取配置文件

```python
# 调用
result = await read_file_tool(
    file_path="config/database.yaml",
    show_line_numbers=True
)

# 返回
ToolTaskResult(
    str_content="""文件内容：config/database.yaml
读取行数：1-15 / 共15行

    1→database:
    2→  host: localhost
    3→  port: 5432
    4→  name: myapp
    5→  user: admin
    6→  password: secret
    7→  pool_size: 10
    8→
    9→redis:
   10→  host: localhost
   11→  port: 6379
   12→  db: 0
   13→
   14→logging:
   15→  level: INFO
""",
    occur_error=False
)
```

## 示例 7：分页读取大文件

```python
# 第一次读取
result = await read_file_tool(
    file_path="data/large.csv",
    offset=0,
    limit=100,
    show_line_numbers=False
)

# 返回前 100 行
# ... 用户处理后 ...

# 第二次读取（继续）
result = await read_file_tool(
    file_path="data/large.csv",
    offset=100,
    limit=100,
    show_line_numbers=False
)

# 返回第 101-200 行
```

## 示例 8：路径包含隐藏组件（UserSpaceFileBackend）

```python
# 调用
result = await read_file_tool(
    file_path=".env"  # 隐藏文件
)

# 返回
ToolTaskResult(
    str_content="""读取文件失败：路径包含隐藏组件，不允许访问：.env
""",
    occur_error=True
)
```

## 示例 9：隐藏目录中的文件（UserSpaceFileBackend）

```python
# 调用
result = await read_file_tool(
    file_path=".ssh/config"  # 隐藏目录中的文件
)

# 返回
ToolTaskResult(
    str_content="""读取文件失败：路径包含隐藏组件，不允许访问：.ssh/config
""",
    occur_error=True
)
```

## 示例 10：使用不同存储后端

```python
# MemoryFileBackend（测试）
result = await read_file_tool(
    file_path="test.txt"
)

# LocalFileBackend（本地测试）
result = await read_file_tool(
    file_path="/tmp/test/file.txt"
)

# UserSpaceFileBackend（生产环境）
result = await read_file_tool(
    file_path="documents/report.pdf"
)
```
