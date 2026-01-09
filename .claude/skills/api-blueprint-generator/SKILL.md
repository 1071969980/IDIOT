---
skill_name: api_blueprint_generator
skill_description: API Blueprint 文档生成器。用户可能通过以下方式暗示使用此 skill: "生成 API 文档"、"创建 API Blueprint"、"从代码生成文档"、"验证 API 文档"、"写 API 文档"、"API 文档化"
---

# API Blueprint 文档生成器 Skill

当用户调用此 skill 时，你将帮助用户生成、创建或验证 API Blueprint 规范文档。

## 技能概述

API Blueprint 是一种用于描述 Web API 的文档格式。本 skill 支持三种工作模式：

1. **从现有代码生成** - 分析项目中的 FastAPI 代码，自动生成 API Blueprint 文档
2. **交互式创建** - 通过对话引导用户逐步输入 API 信息，生成 API Blueprint 文档
3. **文档验证** - 验证现有 API Blueprint 文档的语法正确性，更详细的 MSON 语法请查看 [MSON_cheatsheet.md](MSON_cheatsheet.md)

## 工作流程

### 步骤 1: 确定工作模式

根据用户的请求，判断应该使用哪种模式：

- 用户提到"代码生成"、"从代码生成"或指定模块名称 → 使用**代码生成模式**
- 用户提到"创建"、"新建"或描述新的 API 需求 → 使用**交互式创建模式**
- 用户提到"验证"、"检查"或指定现有 .apib 文件 → 使用**文档验证模式**
- 无法明确判断 → 使用 AskUserQuestion 工具询问用户

### 步骤 2: 执行对应模式的流程

---

## 模式 1: 从现有代码生成

### 你的任务

分析项目中的 FastAPI 代码，生成 API Blueprint 文档。

### 工作流程

1. **确认目标模块**
   - 如果用户未指定，询问用户要生成哪个模块的文档
   - 或使用 Glob 工具扫描 `api/app/*/` 目录，列出可用模块供用户选择

2. **扫描和解析代码**
   - 使用 Glob 查找目标模块的文件：
     - `api/app/{module}/router_declare.py` - 路由声明
     - `api/app/{module}/data_model.py` - 数据模型
     - `api/app/{module}/endpoints.py` - 端点实现
   - 使用 Read 工具读取这些文件

3. **提取 API 信息**
   从代码中提取以下信息：
   - API 名称（从模块名或文档字符串）
   - 路由前缀 (APIRouter prefix)
   - 每个 HTTP 端点：
     - 方法 (GET, POST, PUT, DELETE, PATCH)
     - 路径
     - Path 参数 (Path(...))
     - Query 参数 (Query(...))
     - Request Body (request model)
     - Response 状态码和模型
   - Pydantic 模型定义（字段名、类型、描述、验证规则）

4. **生成 API Blueprint 文档**
   按照以下模板结构生成文档：
   ```
   FORMAT: 1A

   # {API 名称}

   {API 描述}

   # Group {资源组名}

   ## {资源名} [{路径}]

   ### {动作名} [HTTP方法]

   + Parameters
       + {参数名} ({类型}) - {描述}

   + Response {状态码} (application/json)

           {响应体}
   ```

5. **保存文档**
   - 确认 `docs/api/` 目录存在
   - 保存为 `docs/api/{module_name}.apib`
   - 向用户报告生成结果

### FastAPI 到 API Blueprint 的映射

| FastAPI 代码 | API Blueprint 输出 |
|-------------|-------------------|
| `APIRouter(prefix="/users")` | `# Group 用户` + `## 用户资源 [/users]` |
| `@router.get("/")` | `### 获取用户列表 [GET]` |
| `@router.get("/{id}")` | `### 获取单个用户 [GET]` + `+ Parameters` |
| `id: int = Path(...)` | `+ id (number) - 用户ID` |
| `limit: int = Query(10)` | `+ limit (number, optional) - 限制数量` |
| `status_code=201` | `+ Response 201` |
| `response_model=UserSchema` | `+ Response 200 (application/json)` + schema |
| Pydantic Field(description="...") | 参数/字段描述 |

### Pydantic 类型映射

| Python 类型 | API Blueprint 类型 |
|------------|-------------------|
| int, float | number |
| str | string |
| bool | boolean |
| list, List | array |
| dict, Dict | object |
| datetime | string (ISO 8601) |
| Literal[...] | enum |

---

## 模式 2: 交互式创建

### 你的任务

通过对话引导用户输入 API 信息，逐步构建完整的 API Blueprint 文档。

### 工作流程

1. **收集基本信息**
   使用 AskUserQuestion 或直接询问：
   - API 名称
   - API 描述
   - 基础路径（可选，默认 /api/v1）

2. **收集资源组信息**
   - 询问需要定义哪些资源组
   - 对每个资源组收集描述

3. **逐个收集资源定义**
   对每个资源组：
   - 询问资源名称和 URI 路径
   - 询问支持的 HTTP 方法
   - 对每个方法收集详细信息

4. **收集方法详细信息**
   对每个 HTTP 方法：
   - 询问方法描述
   - 询问是否需要参数：
     - URI 参数（从路径中提取 {param}）
     - Query 参数
   - 询问请求体（POST/PUT/PATCH）
   - 询问响应（成功和错误）
   - 询问请求/响应的示例数据

5. **生成和保存文档**
   - 根据收集的信息生成完整文档
   - 保存到 `docs/api/{api_name}.apib`
   - 向用户确认并报告结果

### 对话示例

```
用户: 我想创建一个新的 API 文档

你: 好的，让我们开始创建 API Blueprint 文档。
请提供以下信息：

1. API 名称是什么？
2. 这个 API 的用途是什么？

[用户回答后继续收集...]

你: 需要定义哪些资源组？（例如：用户、订单、产品）

[用户回答后...]

你: 让我们定义"用户"资源组。
请提供第一个资源的 URI 路径（例如：/users）
```

---

## 模式 3: 文档验证

### 你的任务

验证现有 API Blueprint 文档的语法正确性，生成验证报告。

### 工作流程

1. **定位文档**
   - 如果用户未指定，使用 Glob 查找 `docs/api/*.apib` 文件
   - 读取指定的 .apib 文件

2. **执行验证检查**

   **格式检查**:
   - [ ] 文件开头是否包含 `FORMAT: 1A`
   - [ ] 标题层级是否正确（#, ##, ###）
   - [ ] URI 模板语法是否正确（{/path} 格式）

   **结构检查**:
   - [ ] 每个 Action（### 开头）是否至少有一个 Response
   - [ ] Response 是否包含状态码（3位数字）
   - [ ] URI 参数是否在 + Parameters 块中定义
   - [ ] 资源 URI 是否定义（## Resource [/path]）

   **语法检查**:
   - [ ] 列表项格式是否正确（+, *, - 开头）
   - [ ] 代码块缩进是否正确（8个空格）
   - [ ] 媒体类型格式是否正确（application/json 等）
   - [ ] 中文编码是否正常

3. **生成验证报告**
   格式化输出：
   ```
   验证报告：{文件名}

   格式检查：
   ✓ FORMAT: 1A 头部存在
   ✓ 标题层级正确
   ⚠ 第 N 行：URI 模板可能缺少参数定义

   结构检查：
   ✓ 所有 Action 都有 Response
   ✗ GET /posts 缺少 page 参数的描述

   语法检查：
   ✓ 列表项格式正确
   ✗ 第 45 行：缩进错误（应为 8 个空格）

   总结：发现 X 个错误，Y 个警告
   ```

---

## API Blueprint 语法参考

### 基本结构模板

```apib
FORMAT: 1A

# API 名称

API 描述文本，可以多段。

# Group 资源组名称

资源组描述。

## 资源名称 [/uri/path]

资源描述。

### 动作名称 [HTTP_METHOD]

动作描述。

+ Parameters
    + param_name (type, optional) - 参数描述

+ Request (application/json)

        {
            "key": "value"
        }

+ Response 200 (application/json)

        [
            {
                "id": 1
            }
        ]
```

### 完整示例

```apib
FORMAT: 1A

# 博客 API

简单的博客系统 API。

# Group 文章

文章管理相关资源。

## 文章列表 [/posts]

文章集合资源。

### 获取文章列表 [GET]

支持分页查询。

+ Parameters
    + page (number, optional) - 页码，默认 1
    + limit (number, optional) - 每页数量，默认 10

+ Response 200 (application/json)

        [
            {
                "id": 1,
                "title": "文章标题",
                "content": "文章内容",
                "author": "作者",
                "created_at": "2024-01-01T00:00:00Z"
            }
        ]

### 创建文章 [POST]

+ Request (application/json)

        {
            "title": "标题",
            "content": "内容",
            "author": "作者"
        }

+ Response 201 (application/json)

    + Headers

            Location: /posts/1

    + Body

            {
                "id": 1,
                "title": "标题",
                "content": "内容",
                "author": "作者",
                "created_at": "2024-01-01T00:00:00Z"
            }

+ Response 400 (application/json)

        {
            "error": "invalid_input",
            "message": "请求数据无效"
        }

## 单个文章 [/posts/{id}]

+ Parameters
    + id (number) - 文章 ID

### 获取文章详情 [GET]

+ Response 200 (application/json)

        {
            "id": 1,
            "title": "文章标题",
            "content": "文章内容",
            "author": "作者",
            "created_at": "2024-01-01T00:00:00Z"
        }

+ Response 404 (application/json)

        {
            "error": "not_found",
            "message": "文章不存在"
        }

### 更新文章 [PUT]

+ Request (application/json)

        {
            "title": "新标题",
            "content": "新内容"
        }

+ Response 200 (application/json)

        {
            "id": 1,
            "title": "新标题",
            "content": "新内容",
            "author": "作者",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z"
        }

### 删除文章 [DELETE]

+ Response 204

+ Response 404 (application/json)

        {
            "error": "not_found",
            "message": "文章不存在"
        }

## Data Structures

### Article
+ id: 1 (number) - 文章 ID
+ title: `标题` (string) - 文章标题
+ content: `内容` (string) - 文章内容
+ author: `作者` (string) - 作者名称
+ created_at: `2024-01-01T00:00:00Z` (string) - 创建时间
+ updated_at: `2024-01-01T00:00:00Z` (string) - 更新时间

### Error
+ error: `invalid_input` (string) - 错误代码
+ message: `描述` (string) - 错误描述
```

### 语法速查表

| 元素 | 语法 | 示例 |
|------|------|------|
| 元数据 | `FORMAT: 1A` | 版本声明 |
| API 名称 | `# 名称` | 一级标题 |
| 资源组 | `# Group 名称` | 分组关键字 |
| 资源 | `## 名称 [/path]` | URI 在方括号 |
| URI 参数 | `{param}` | 花括号表示 |
| 动作 | `### 名称 [METHOD]` | HTTP 方法 |
| 参数块 | `+ Parameters` | 参数列表开始 |
| 参数 | `+ name (type)` | 定义参数 |
| 可选参数 | `(type, optional)` | 添加 optional |
| 请求 | `+ Request (type)` | 定义请求 |
| 响应 | `+ Response code (type)` | 定义响应 |
| 头部 | `+ Headers` | 响应头块 |
| 代码块 | 8 空格缩进 | JSON 等数据 |

### 数据类型

| 类型 | 说明 | 示例值 |
|------|------|--------|
| string | 字符串 | `"text"` |
| number | 数字 | `42`, `3.14` |
| boolean | 布尔 | `true`, `false` |
| array | 数组 | `[1, 2]` |
| object | 对象 | `{"k": "v"}` |
| enum | 枚举 | 列出可选值 |

### HTTP 方法与状态码

| 方法 | 说明 | 常用状态码 |
|------|------|-----------|
| GET | 获取 | 200, 404 |
| POST | 创建 | 201, 400, 409 |
| PUT | 完整更新 | 200, 204, 404 |
| PATCH | 部分更新 | 200, 204, 404 |
| DELETE | 删除 | 204, 404 |

### 常用状态码

- `200` - OK
- `201` - Created
- `204` - No Content
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `409` - Conflict
- `500` - Internal Server Error

### 常用媒体类型

- `application/json` - JSON
- `application/xml` - XML
- `text/plain` - 纯文本
- `application/x-www-form-urlencoded` - 表单
- `multipart/form-data` - 多部分表单

---

## 输出规范

- **输出目录**: `docs/api/`
- **文件扩展名**: `.apib`
- **文件命名**:
  - 代码生成: `{module_name}.apib`
  - 交互式创建: `{api_name}.apib`（基于用户输入）
- **编码**: UTF-8

---

## 注意事项

1. **确保目录存在**: 在保存文件前，检查 `docs/api/` 目录是否存在，不存在则创建
2. **缩进规范**: API Blueprint 的代码块（JSON 等）必须使用 8 个空格缩进
3. **参数完整性**: URI 模板中的参数（如 `{id}`）必须在 `+ Parameters` 块中定义
4. **响应必需**: 每个 Action 必须至少有一个 Response
5. **媒体类型**: 在 Request/Response 后的括号中指定媒体类型
6. **中文支持**: 确保文件以 UTF-8 编码保存

---

## 调试建议

如果生成的文档不符合预期：
1. 检查 FastAPI 代码的文档字符串（docstrings）
2. 确认 Pydantic 模型的 Field 描述是否完整
3. 验证路由前缀和路径参数是否正确解析
4. 使用外部工具（如 API Blueprint 验证器）验证生成的文档
