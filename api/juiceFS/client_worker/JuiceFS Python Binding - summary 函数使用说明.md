# JuiceFS Python Binding - summary 函数使用说明

## 函数签名

```python
def summary(self, path, depth=0, entries=1)
```

## 参数

| 参数   | 类型 | 默认值 | 说明                                                     |
|--------|------|--------|----------------------------------------------------------|
| path   | str  | 必填   | 要统计的目录或文件路径                                   |
| depth  | int  | 0      | 递归深度，0 表示只返回当前目录的汇总，不展开子目录      |
| entries| int  | 1      | 每层返回的子条目数（TopN），按 Size 降序排列            |

### 参数限制

- **depth** 最大值为 **255**（Go 侧类型为 `uint8`），不支持无限深度
- **entries** 最大值为 **4294967295**（Go 侧类型为 `uint32`），但设过大会导致返回数据量很大

## 返回值

返回 dict，结构如下：

```json
{
  "Path": "/data",
  "Type": 1,
  "Size": 1048576,
  "Files": 100,
  "Dirs": 5,
  "Children": [...]
}
```

| 字段     | 说明                                                        |
|----------|-------------------------------------------------------------|
| Path     | 条目路径                                                    |
| Type     | 文件类型，取值见下表                                        |

### Type 字段取值

| Type 值 | 含义            | 说明                                        |
|---------|-----------------|---------------------------------------------|
| 1       | 普通文件        |                                             |
| 2       | 目录            |                                             |
| 3       | 符号链接        |                                             |
| 4       | FIFO（命名管道）|                                             |
| 5       | 块设备          |                                             |
| 6       | 字符设备        |                                             |
| 7       | Socket          |                                             |

> 定义在 `pkg/meta/interface.go:62-69`。在 summary 返回中最常见的是 1（文件）和 2（目录）。被 entries 裁剪后合并的省略条目（`Path: "..."`），其 Type 会被设为 1。
| Size     | 该条目及其子树占用的总大小（字节，按 4K 对齐）             |
| Files    | 文件数量                                                    |
| Dirs     | 子目录数量                                                  |
| Children | 子条目列表，仅在 `depth > 0` 且 `Dirs > 0` 时存在         |

Python 侧会自动移除 `Inode` 字段，以及 `Dirs == 0` 时移除空的 `Children`。

## 使用示例

```python
from juicefs import Client

client = Client("myvol", meta="redis://localhost/0")

# 只看顶层汇总
s = client.summary("/data")
# {"Path": "/data", "Type": 1, "Size": ..., "Files": ..., "Dirs": ...}

# 展开一层，显示占用最大的前 5 个子条目
s = client.summary("/data", depth=1, entries=5)

# 展开两层，每层显示前 10 个
s = client.summary("/data", depth=2, entries=10)
```

## 目录和文件的处理差异

| 条目类型 | 是否在 Children 中返回 | 是否递归子树 | 返回的信息                       |
|----------|------------------------|-------------|----------------------------------|
| 目录     | 是                     | 是          | 完整汇总 + Children（如果有子树）|
| 普通文件 | 是                     | 否          | Type, Path, Size, Files=1        |

目录和普通文件都会出现在 `Children` 中，但只有目录会被继续递归展开。

## TopN 机制

当 `depth > 0` 时，Go 侧会收集当前目录下所有条目，按 `Size` 降序排序，只保留前 `entries` 个。
超出部分会被合并为一个 `Path: "..."` 的汇总条目，包含被省略条目的合计 Size/Files/Dirs。

```python
# entries=2 时，假设 /data 下有 a, b, c, d 四个子目录
s = client.summary("/data", depth=1, entries=2)
# Children 可能是：
# [
#   {Path: "/data/a", Size: 1000, ...},   # 最大的
#   {Path: "/data/b", Size: 800, ...},    # 第二大
#   {Path: "/data/...", Size: 500, ...},  # c + d 的合计
# ]
```

## depth 行为详解

```
depth=0 → 不展开，只返回当前目录的汇总数字（Size/Files/Dirs）
depth=1 → 展开一层，返回直接子条目的汇总
depth=2 → 展开两层，子条目的子条目也会展开
depth=N → 展开 N 层
depth=255 → 最大深度
```

## 注意事项

1. **性能**：depth 越大、目录树越深，耗时越长。Go 侧使用最多 50 个 goroutine 并发遍历
2. **Size 按 4K 对齐**：返回的 Size 是 `align4K(length)`，即使文件只有 1 字节也会按 4096 计算
3. **大目录建议**：先用小 depth（如 1-2）定位占用最大的子目录，再逐步深入
4. **路径可以是文件**：如果 path 指向普通文件，会返回该文件的 Size/Files=1，不会报错

## 相关源码

| 文件                              | 位置         | 说明                          |
|-----------------------------------|-------------|-------------------------------|
| sdk/python/juicefs/juicefs/juicefs.py | 第 400 行    | Python 侧 summary 定义        |
| sdk/java/libjfs/main.go           | 第 1491 行   | Go 侧 jfs_gettreesummary 导出 |
| pkg/meta/utils.go                 | 第 496 行    | GetTreeSummary 核心实现       |
| pkg/meta/interface.go             | 第 323 行    | TreeSummary 数据结构定义      |
| pkg/fs/fs.go                      | 第 1535 行   | File.GetTreeSummary 封装      |
