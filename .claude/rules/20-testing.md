---
description: LLM Wiki 测试规范 — 结构/Mock/覆盖/运行
globs: tests/**/*.py
---

# 测试规范

## 测试目录结构

```
tests/
├── conftest.py          # 共享 Fixture
├── test_core/           # 核心逻辑测试
│   ├── test_wiki_compiler.py
│   └── test_memory.py
├── test_tools/          # 工具测试
│   ├── test_read_tool.py
│   ├── test_write_tool.py
│   └── test_search_tool.py
├── test_llm/            # LLM 适配器测试
│   └── test_adapter.py
├── test_db/             # 数据库层测试
│   └── test_repository.py
└── test_api/            # API 集成测试
    └── test_main.py
```

## 测试原则

- 使用 `pytest`，禁止使用 `unittest`
- 测试文件名以 `test_` 开头
- 测试函数名以 `test_` 开头
- 一个测试只测一个行为

## Mock 策略

- LLM 调用全部 Mock，不实际调 API
- 文件系统操作使用 `tmp_path` fixture
- 数据库使用 `:memory:` 模式

```python
# ✅ 正确 — Mock LLM
def test_ingest(mocker, tmp_path):
    mock_llm = mocker.patch("src.llm.adapter.LLMAdapter.chat")
    mock_llm.return_value = "# 测试页面"
    
    compiler = WikiCompiler()
    result = compiler.ingest("test.md")
    assert result["status"] == "success"
```

## 边界情况覆盖

每个测试文件必须覆盖：

1. **正常路径** — 正确输入得到正确输出
2. **边界条件** — 空列表、大文件、特殊字符
3. **错误路径** — 路径穿越、权限拒绝、文件不存在
4. **LLM 异常** — 超时、空回复、格式错误

## 运行

```bash
# 运行全部测试
pytest

# 运行单个文件
pytest tests/test_tools/test_read_tool.py -v

# 带覆盖率
pytest --cov=src --cov-report=term-missing
```

- 提交前必须通过 `pytest` 全部测试
- 新功能必须包含对应测试
