---
description: LLM Wiki 安全规则 — 路径权限校验、输入验证、Agent 边界
globs: src/**/*.py
---

# 安全规则

## 核心原则

LLM Wiki 的核心安全模型基于**目录隔离**：

| 目录 | 权限 | 说明 |
|------|------|------|
| `raw/` | **只读** | 原始素材，任何 Agent 不能修改 |
| `wiki/` | **读写** | LLM 维护的知识层，Agent 可写 |
| `src/` | **只读** | 代码由人类维护，Agent 可读不可改 |
| `.claude/` | **只读** | 配置规则由人类维护 |

## 路径前缀校验

所有工具调用**必须**做路径前缀校验，防止路径穿越攻击：

```python
# ✅ 正确 — 显式校验
ALLOWED_PREFIXES = {"wiki", "raw"}
actual = os.path.normpath(path).lstrip("./")
if not any(actual.startswith(p + "/") for p in ALLOWED_PREFIXES):
    raise PermissionError(f"Access denied: {path}")

# ❌ 错误 — 未校验
open(path).read()
```

## 路径穿越防御

```python
import os

def safe_path(base_dir: str, user_path: str) -> str:
    """安全拼接路径，防止 ../ 穿越"""
    # 规范化，拒绝绝对路径
    if os.path.isabs(user_path):
        raise PermissionError("Absolute path not allowed")
    full = os.path.normpath(os.path.join(base_dir, user_path))
    # 校验最终路径仍在前缀之内
    if not full.startswith(os.path.normpath(base_dir)):
        raise PermissionError("Path traversal detected")
    return full
```

## LLM 输出验证

LLM 生成的 Wiki 页面内容写入前必须校验：

- 文件名不能包含 `../` 或空路径
- Markdown 内容不允许嵌入可执行脚本（`<script>`、`<iframe>` 等）
- 页面类型必须在 `entity / concept / source / query` 范围内

## 数据库安全

- 使用参数化查询，禁止字符串拼接 SQL
- 用户输入（包括 LLM 生成的文本）必须通过 Pydantic 模型校验后再写入
