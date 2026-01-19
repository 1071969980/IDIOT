---
skill_name: lsp_helper
skill_description: LSP 工具使用助手。用户可能通过以下方式暗示使用此 skill: "使用 LSP 检查"、"查找引用"、"跳转到定义"、"检查函数调用"、"LSP 分析"、"符号查找"、"代码导航"
context: fork
---

# LSP 工具使用指南

本技能帮助你正确使用 LSP 工具，**重点在于避免参数错误导致的误判**。

## 核心原则

> **当 LSP 返回意外结果时，99% 的情况是 `character` 参数错误**

LSP 工具对 `character` 参数非常敏感。错误参数会导致：
- `findReferences` 返回 "No references found"（实际有引用）
- `goToDefinition` 跳转失败
- 任何需要精确定位的操作失败

## 基本范式

```
1. 使用 documentSymbol 获取符号行号
2. 阅读文件估计 character 值，或使用Shell脚本精确计算 character 值，参考 `## 参数验证脚本` 章节。
3. 执行目标 LSP 操作
4. 若返回意外结果 → 返回步骤 2
```

## LSP 操作快速参考

| 操作 | 用途 | character 要求 |
|------|------|----------------|
| `documentSymbol` | 列出文件所有符号 | 不要求精确 |
| `findReferences` | 查找符号引用 | **必须精确** |
| `goToDefinition` | 跳转到定义 | **必须精确** |
| `hover` | 获取类型信息 | **必须精确** |
| `incomingCalls` | 谁调用了此函数 | **必须精确** |
| `outgoingCalls` | 此函数调用了什么 | **必须精确** |

## 异常处理决策树

```
LSP 返回意外结果
    │
    ├─ "No references found"
    │   ├─ 符号确实未使用 → 正常结果
    │   └─ 符号应该被引用 → 验证 character 参数
    │
    ├─ "No call hierarchy item found"
    │   └─ 换用 findReferences / incomingCalls
    │
    └─ 任何失败/空结果
        └─ 验证 character 参数
```

## 参数验证脚本

```bash
bash .claude/skills/lsp-helper/verify_lsp_params.sh <file> <line> <symbol>
```

输出格式：`file:line:character`

## 典型错误场景与处理

### 场景 1: findReferences 返回空，但你知道有引用

**原因**: character 参数错误

**处理**:
```bash
# 1. 先用 documentSymbol 确认行号
LSP(filePath="file.py", line=1, character=1, operation="documentSymbol")
# 输出: my_func (Function) - Line 42

# 2. 验证 character
bash .claude/skills/lsp-helper/verify_lsp_params.sh file.py 42 my_func
# 输出: file.py:42:9

# 3. 重新执行
LSP(filePath="file.py", line=42, character=9, operation="findReferences")
```

### 场景 2: goToDefinition 返回错误位置

**原因**: character 指向了导入语句的末尾而非符号名

**处理**: 重新计算 character，指向符号首字符

### 场景 3: 估算的 character 不工作

**原因**: 缩进不一致、装饰器、多行定义等

**处理**: **永远用 Bash 验证，不要估算**

## 注意事项

1. **禁止使用 Grep**: 用户明确要求使用 LSP 而非 Grep
2. **索引延迟**: LSP 服务器首次运行可能需要索引，首次调用可能返回空
3. **字符计数从 1 开始**: LSP character 参数从 1 开始，不是 0
4. **documentSymbol 是起点**: 不确定位置时先用它获取行号
5. **验证是必须的**: 每次返回意外结果，第一反应是验证参数

## 故障排除检查清单

在得出"符号无引用"或"LSP 失败"的结论前，确认：

- [ ] 使用 `verify_lsp_params.sh` 验证了 character 参数
- [ ] 使用 `documentSymbol` 确认符号存在
- [ ] LSP 服务器已运行（非首次索引）
- [ ] 符号名称拼写完全一致
