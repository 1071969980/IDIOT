# CLAUDE.md

本文件为在此代码库中工作时提供指导。

## 项目概述

IDIOT (Intelligent Development Integrated & Operations Toolkit) 是一个基于 Python 的 AI 应用程序后端工具包。

## 开发环境
   
### Python 环境
- **Python 版本**: 需要 3.13+
- **包管理器**: uv (Astral UV)
- **环境设置**: 
  ```bash
  uv python install 3.13
  uv sync
  ```

## 文档结构

详细的技术文档位于 `docs/` 目录：

使用 Sphinx 构建文档：
```bash
cd docs
make html
```
