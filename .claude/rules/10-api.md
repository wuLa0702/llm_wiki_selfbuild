---
description: LLM Wiki API 开发规范 — 路由/Pydantic/错误/文档
globs: src/main.py, src/api/**/*.py, src/routers/**/*.py
---

# API 开发规范

## 路由规范

- 所有业务路由使用 `/v1/` 前缀
- 健康检查和根路径不需要版本前缀
- 路由名使用 snake_case

```python
@app.get("/v1/ingest")
async def ingest():
    ...

@app.get("/v1/query")
async def query():
    ...
```

## 请求/响应模型

- 全部使用 Pydantic v2 BaseModel 定义
- 请求体使用 `POST`，查询参数使用 `GET`
- 响应中始终包含 `status` 字段

```python
class IngestRequest(BaseModel):
    source_path: str = Field(description="源文件路径（相对于 raw/sources/）")

class IngestResponse(BaseModel):
    status: str
    pages_created: list[str] = []
    pages_updated: list[str] = []
    message: str = ""
```

## 错误响应

统一错误格式：

```python
class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
    code: str = "UNKNOWN"
```

HTTP 状态码使用规范：
- `200` — 成功
- `400` — 参数错误
- `403` — 权限拒绝（路径越权等）
- `404` — 资源不存在
- `500` — 服务器内部错误

## API 文档

- FastAPI 自动生成 OpenAPI，确保 docstring 清晰
- 路径参数、查询参数必须写描述
- 敏感操作标注 `summary` 和 `tags`

## CORS

开发阶段允许所有来源，生产环境限制为白名单。
