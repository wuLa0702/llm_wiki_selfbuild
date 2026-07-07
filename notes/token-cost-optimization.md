# Token 成本控制 — 参考方案与行动计划

> 日期：2026-07-06
> 触发：一天消耗 ¥25（DeepSeek Flash + Pro）

---

## 一、你的消耗分析

¥25/天 是什么概念？按 Flash 输出 ¥2/1M tokens 算，大约烧了 **12.5M 输出 tokens**。

最可能的消耗大户：

| 排名 | 原因 | 估算占比 |
|------|------|---------|
| 🔴 | 开发调试反复调 ingest | ~50% |
| 🔴 | Pro 模型用于简单任务 | ~25% |
| 🟡 | Prompt 过长（源文件 + index 上下文） | ~15% |
| 🟢 | 重复内容未缓存 | ~10% |

---

## 二、立即生效的省钱措施（明天就做）

### 1. 默认用 Flash，Pro 只在降级时一次调用

当前代码已支持降级策略。**降低 Pro 调用比例是最大的省钱点：**

```
当前（推测）: Flash 70% / Pro 30%
目标:        Flash 95% / Pro 5%（仅 Step 1 JSON 解析失败时重试一次）
```

预计日费：¥25 → ¥8-10

### 2. 利用 DeepSeek 前缀缓存（Premix Cache）

你的 System Prompt 在多次 ingest 中是固定的 → DeepSeek 自动缓存。**但前提是 system prompt 放在 messages 数组最前面且内容不变。**

```python
# ✅ 正确 — system prompt 固定在前，触发缓存
messages = [
    {"role": "system", "content": SYSTEM_PROMPT_INGEST_ANALYZE},  # 缓存命中
    {"role": "user", "content": f"现有 Wiki 索引：\n\n{index}"},
    {"role": "user", "content": f"源文件内容：\n\n{source}"},
]
# 缓存命中时输入价格从 ¥1/M → ¥0.07/M（省 ~90%）
```

### 3. 缩小 Step 1 的 index.md 上下文

当前传给 Step 1 的 index.md 可能过长。改为只传摘要：

```python
# ❌ 传完整 index.md（可能 3000+ tokens）
index_context = read_file("wiki/index.md")

# ✅ 只传统计 + 最近 10 个页面标题
index_context = self._index_summary()  # ~500 tokens
```

### 4. 开发调试时用更短的测试源文件

别用 5000 字的完整文章调试——用一个 500 字的短段落验证流程是否跑通。

---

## 三、Phase 3 应加入的优化

| 优化 | 说明 | 预计省 |
|------|------|--------|
| **Token 计数器** | `LLMAdapter` 增加 `token_usage` 统计，每次调用记录输入/输出 token 数 | 先监控 |
| **Ingest 响应中返回 token 消耗** | `IngestResponse.token_usage: {input, output}` | 透明化 |
| **GET /v1/usage** | API 端点，查询当日/本周 token 消耗 | 可追踪 |

---

## 四、参考链接

| 资源 | 链接 |
|------|------|
| DeepSeek 缓存文档 | https://api-docs.deepseek.com/ → Context Caching |
| Pro+Flash 混合工作流 | https://cloud.tencent.cn/developer/article/2686729 |
| 降本65% 监控体系 | https://developer.aliyun.com/article/1740933 |
| 前缀缓存最佳实践 | https://wavespeed.ai/blog/posts/blog-deepseek-v4-context-caching/ |
