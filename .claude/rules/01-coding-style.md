---
description: LLM Wiki 编码规范 — 命名/类型/文档/导入/错误处理
globs: src/**/*.py
---

# 编码风格

## 命名规范

| 元素 | 规范 | 示例 |
|------|------|------|
| 文件/目录 | `snake_case` | `wiki_compiler.py` |
| 函数/方法 | `snake_case` | `def ingest_source():` |
| 类 | `PascalCase` | `class WikiCompiler:` |
| 变量 | `snake_case` | `source_path` |
| 常量 | `UPPER_SNAKE` | `ALLOWED_PREFIXES` |
| API 路由 | `/v1/` 前缀 | `/v1/ingest` |

## 类型注解

所有函数签名必须包含类型注解：

```python
# ✅ 正确
def ingest(self, source_path: str) -> dict[str, Any]:
    ...

# ❌ 错误
def ingest(self, source_path):
    ...
```

## 文档字符串

每个模块、类、公开函数必须有 docstring：

```python
"""模块/文件的简短说明"""

class WikiCompiler:
    """一句话说明类职责"""

    def ingest(self, source_path: str) -> dict:
        """
        功能描述

        Args:
            source_path: 参数说明

        Returns:
            返回值说明

        Raises:
            ValueError: 异常场景
        """
```

## 导入顺序

每组之间空一行，顺序如下：

```python
# 1. 标准库
import os
from pathlib import Path

# 2. 第三方库
from fastapi import FastAPI
from pydantic import BaseModel

# 3. 项目内部
from src.core.models import WikiPage
```

## 错误处理

- 使用自定义异常类，不应直接 `raise Exception`
- 工具方法返回 `Result` 模式或抛出明确的异常
- LLM 调用必须加超时和重试

## 代码组织

- 一个文件不超过 300 行
- 一个类不超过 200 行
- 一个函数不超过 50 行
