# 阶段测试报告 — Phase 3 前端其余页面 + 边界补漏

| 项 | 值 |
|----|----|
| 阶段 | Phase 3 — 前端其余页面 + 边界补漏（M5） |
| 执行时间 | 2026-08-01 |
| 执行人 | [ui-deepseek-flash/deepseek-v4-flash🐾] |
| 基线 | 后端 738 passed / 前端 53 passed（Phase 2 结束） |

## 一、覆盖范围

对应 TEST-PLAN.md Phase 3，模块 M5：

1. **WikiPage**：Markdown 渲染、wikilink 导航、加载/空/错误态、文件树选择、正向引用 chip
2. **SearchPage**：搜索请求、置信度 Pill、关键词高亮、多命中展开、分页、模式切换、图例条
3. **GraphPage**：vis-network 渲染（mock）、加载/空/错误态、节点/链接计数、communities/insights 静默降级
4. **HomePage**：统计卡、快捷入口导航、最近页面、系统状态、接口失败容错
5. **后端边界**：特殊字符路径、空文件、超大文件、路径穿越、并发上传

## 二、执行结果

| 层 | 新增用例 | 全量用例 | 通过 | 失败 | 通过率 |
|----|---------|---------|------|------|--------|
| 后端 | 13（test_boundary.py） | 751 | 751 | 0 | 100% |
| 前端 | 28（HomePage 7 + SearchPage 8 + WikiPage 6 + GraphPage 5 + 回归 2 组） | **81** | 81 | 0 | 100% |

前端用例 53 → 81，**超过验收线 ~50+**；tsc 0 错误。

新增测试文件：
- `wiki-ui-v2/src/pages/__tests__/HomePage.test.tsx`（7 用例）
- `wiki-ui-v2/src/pages/__tests__/SearchPage.test.tsx`（8 用例）
- `wiki-ui-v2/src/pages/__tests__/WikiPage.test.tsx`（6 用例）
- `wiki-ui-v2/src/pages/__tests__/GraphPage.test.tsx`（5 用例）
- `tests/test_api/test_boundary.py`（13 用例）

## 三、发现的问题

| # | 严重度 | 问题 | 状态 |
|---|--------|------|------|
| 1 | P3 | 观察项：GraphPage 的 `insights` 区块直接访问 `insights.summary.total_surprising`，若后端返回缺 summary 字段的对象会崩（真实后端恒有 summary，风险极低） | 观察（可加防御） |

## 四、验证证据

- 全量回归：`pytest` → 751 passed（新增 13）；`vitest run` → 81 passed（11 文件）；`tsc -b` → 0 错误
- 边界测试要点：
  - 特殊字符（中文/空格/#）tree → file-content → delete 全链路 200
  - 空文件 size=0、content 为空字符串
  - 1.5MB 文件完整返回不截断（首尾内容抽查）
  - 路径穿越（`../`、绝对路径）在 file-content / delete / extract / check-changed 四处全部 403
  - 并发 4 线程 × 2 文件上传：saved=8、落盘 8 个文件内容逐字校验、穿越文件名（`../../evil.md`）被跳过
- 前端测试要点：SearchPage 过滤 score<0.1 结果、多命中展开、offset 翻页；GraphPage 用 class mock 构造 vis-network（`new` 需要 class 而非 vi.fn）并记录实例数；HomePage 接口失败统计归零不崩溃

## 五、遗留事项

- GraphPage insights 防御性空值判断（可选优化，非阻塞）
- Phase 4 端到端冒烟（M6）待执行

## 六、结论

✅ **达成**：后端 751 passed 全绿 + 前端 81 用例绿（≥ ~50 验收线）+ tsc 0 错误。可进入 Phase 4。
