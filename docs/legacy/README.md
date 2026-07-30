# Legacy / 归档

此目录存放项目迭代过程中淘汰的旧版本文件，供历史参考。

## 文件清单

| 文件 | 来源 | 弃用原因 |
|------|------|---------|
| `wiki.spec.old` | 项目根目录 `wiki.spec` | 缺少 `src.agent.*`、`src.api.routes.chat/ingest/purpose/system` 等大量模块，无法正确打包当前项目。构建脚本已使用 `wiki-llm.spec`。 |
