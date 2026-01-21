# edit_file 工具使用示例

## 示例 1：单次替换（内容唯一）

```python
# 调用
result = await edit_file_tool(
    file_path="src/main.py",
    old_string='def hello_world():',
    new_string='def hello_universe():'
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/main.py\n替换了 1 处内容",
    occur_error=False
)
```

## 示例 2：全局替换

```python
# 调用
result = await edit_file_tool(
    file_path="src/config.py",
    old_string='"localhost"',
    new_string='"127.0.0.1"',
    replace_all=True
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/config.py\n替换了 5 处内容",
    occur_error=False
)
```

## 示例 3：重复内容检测（错误）

```python
# 调用
result = await edit_file_tool(
    file_path="src/utils.py",
    old_string='print("debug")',
    new_string='# print("debug")',
    replace_all=False  # 未设置 replace_all
)

# 返回
ToolTaskResult(
    str_content="""编辑文件失败：old_string 在文件中出现多次（共3次）。

如果要替换所有匹配项，请设置 replace_all=true。

匹配位置预览：
第1处：第15行
第2处：第28行
第3处：第43行
""",
    occur_error=True
)
```

## 示例 4：内容不存在

```python
# 调用
result = await edit_file_tool(
    file_path="src/main.py",
    old_string='def deprecated_function():',
    new_string='# removed'
)

# 返回
ToolTaskResult(
    str_content="编辑文件失败：未找到要替换的内容：def deprecated_function():",
    occur_error=True
)
```

## 示例 5：删除内容

```python
# 调用
result = await edit_file_tool(
    file_path="src/legacy.py",
    old_string='# TODO: remove this\n',
    new_string=''  # 空字符串表示删除
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/legacy.py\n替换了 1 处内容",
    occur_error=False
)
```

## 示例 6：多行替换

```python
# 调用
result = await edit_file_tool(
    file_path="src/models.py",
    old_string='''class OldModel:
    """旧的模型"""
    pass''',
    new_string='''class NewModel:
    """新的模型"""
    def __init__(self):
        self.data = {}'''
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/models.py\n替换了 1 处内容",
    occur_error=False
)
```

## 示例 7：替换配置值

```python
# 调用
result = await edit_file_tool(
    file_path="config/settings.yaml",
    old_string='debug: false',
    new_string='debug: true'
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：config/settings.yaml\n替换了 1 处内容",
    occur_error=False
)
```

## 示例 8：替换导入语句

```python
# 调用
result = await edit_file_tool(
    file_path="src/app.py",
    old_string='from old_package import function',
    new_string='from new_package import function'
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/app.py\n替换了 1 处内容",
    occur_error=False
)
```

## 示例 9：文件不存在

```python
# 调用
result = await edit_file_tool(
    file_path="nonexistent.py",
    old_string='old',
    new_string='new'
)

# 返回
ToolTaskResult(
    str_content="编辑文件失败：文件不存在：nonexistent.py",
    occur_error=True
)
```

## 示例 10：路径包含隐藏组件（UserSpaceFileBackend）

```python
# 调用
result = await edit_file_tool(
    file_path=".git/config",  # 隐藏文件
    old_string='old',
    new_string='new'
)

# 返回
ToolTaskResult(
    str_content="编辑文件失败：路径包含隐藏组件，不允许访问：.git/config",
    occur_error=True
)
```

## 示例 11：重复内容确认后替换

```python
# 第一次尝试（错误）
result = await edit_file_tool(
    file_path="src/logger.py",
    old_string='logger.info("processing")',
    new_string='logger.debug("processing")',
    replace_all=False
)
# 返回错误：内容重复出现 5 次

# 第二次尝试（设置 replace_all）
result = await edit_file_tool(
    file_path="src/logger.py",
    old_string='logger.info("processing")',
    new_string='logger.debug("processing")',
    replace_all=True  # 现在允许替换所有
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/logger.py\n替换了 5 处内容",
    occur_error=False
)
```

## 示例 12：替换为空（删除）

```python
# 删除注释
result = await edit_file_tool(
    file_path="src/code.py",
    old_string='# This is a comment\n',
    new_string=''  # 删除注释行
)

# 返回
ToolTaskResult(
    str_content="成功编辑文件：src/code.py\n替换了 1 处内容",
    occur_error=False
)
```

## 示例 13：精确匹配（不支持正则）

```python
# 以下调用会失败，因为 old_string 必须精确匹配
result = await edit_file_tool(
    file_path="src/data.py",
    old_string=r'def \w+\(',  # 正则表达式，不支持
    new_string='def function('
)

# 返回
ToolTaskResult(
    str_content="编辑文件失败：未找到要替换的内容：def \\w+(",
    occur_error=True
)
```

## 示例 14：并发编辑（分布式锁保护）

```python
# 两个 Agent 同时编辑同一文件

# Agent 1
result1 = await edit_file_tool(
    file_path="shared.txt",
    old_string="value1",
    new_string="value2"
)

# Agent 2（同时执行）
result2 = await edit_file_tool(
    file_path="shared.txt",
    old_string="value3",
    new_string="value4"
)

# UserSpaceFileBackend 使用分布式锁，确保操作串行执行
# 其中一个操作会等待锁释放后再执行
```
