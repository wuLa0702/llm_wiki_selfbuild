# 前端迁移方案：htmx + Jinja2 → React + HeroUI + Vite

> **现状**：FastAPI Jinja2 模板 + htmx 局部刷新 + 手写 CSS
> **目标**：React 18 + TypeScript + HeroUI + Tailwind CSS + Vite

---

## 一、技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 构建 | Vite 6 | 最快的前端构建工具，HMR 秒级 |
| 框架 | React 18 + TypeScript | Strict mode |
| UI | HeroUI v2 | Tailwind 生态，按需加载 |
| 样式 | Tailwind CSS 4 | Utility-first |
| 路由 | react-router-dom v7 | 前端路由 |
| HTTP | fetch（原生） | 或 ky（轻量封装） |
| Markdown | marked + highlight.js | 维持现有方案 |
| 图表 | @antv/g6（重构） | 图谱可视化 |

## 二、目录结构

```
wiki-ui/                          ← 新建目录，和 src/ 同级
├── index.html                    # Vite 入口
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
└── src/
    ├── main.tsx                  # React 入口
    ├── App.tsx                   # 路由 + 全局布局
    ├── api/
    │   └── client.ts             # fetch 封装层（所有 API 调用集中）
    ├── components/               # 全局复用组件
    │   ├── Layout.tsx            # 三栏布局（侧栏 + 内容区）
    │   ├── Sidebar.tsx           # 图标侧栏
    │   ├── TreePanel.tsx         # 知识库树 + 文件树
    │   ├── TaskQueue.tsx         # 任务队列面板
    │   └── WikiContent.tsx       # Markdown 渲染
    ├── pages/
    │   ├── HomePage.tsx          # 首页 / 知识库
    │   ├── SourcesPage.tsx       # 资料源
    │   ├── GraphPage.tsx         # 图谱
    │   ├── QueryPage.tsx         # 问答
    │   ├── SettingsPage.tsx      # 设置
    │   ├── PageView.tsx          # Wiki 页面查看
    │   └── NotFound.tsx          # 404
    └── hooks/
        ├── useApi.ts             # 通用 API 请求 hook
        └── usePolling.ts         # 轮询 hook（队列状态）
```

## 三、页面与 API 对照

| 路由 | 页面 | 主要 API |
|------|------|----------|
| `/` | 知识库首页 | `GET /v1/pages`, `GET /v1/lint` |
| `/page/*` | Wiki 页面查看 | `GET /v1/pages/{path}` |
| `/sources` | 资料源 | `GET /v1/sources/tree`, `GET /v1/ingest/queue/recent` |
| `/graph` | 图谱 | `GET /v1/graph`, `GET /v1/communities` |
| `/query` | 问答 | `POST /v1/query` |
| `/settings` | 设置 | `GET/POST /v1/settings`, `GET/POST /v1/watcher/*` |
| `/health` | 健康检查 | `GET /health` |

## 四、后端改造

后端需新增一个入口 HTML（移除 Jinja2 渲染），改为 SPA：

```python
# src/main.py 新增
from fastapi.staticfiles import StaticFiles

# SPA 入口 — 所有前端路由返回 index.html
app.mount("/ui", StaticFiles(directory="wiki-ui/dist", html=True), name="ui")
```

同时现有 `/wiki/*` 路由可以保留为 API 重定向，逐步废弃。

## 五、迁移步骤

### Phase 1：基建（1 天）

```
1. 创建 wiki-ui/，Vite + React + TypeScript 初始化
2. 安装 HeroUI + Tailwind CSS
3. 配置 vite.config.ts（代理 /v1/* → FastAPI）
4. 实现 Layout + Sidebar + TreePanel 基础组件
5. 实现路由框架 + API client
```

### Phase 2：核心页面（2 天）

```
6. HomePage — 知识库树 + 文件树（复用现有 API）
7. SourcesPage — 文件列表 + 预览 + 任务队列
8. WikiContent — Markdown 渲染（marked + highlight.js）
```

### Phase 3：次要页面（1 天）

```
9. GraphPage — 图谱可视化
10. QueryPage — 问答交互
11. SettingsPage — 设置表单
```

### Phase 4：收尾（1 天）

```
12. 暗色模式切换
13. 删除旧模板（src/api/templates/）
14. 清理 static/ 下已迁移的文件
```

## 六、注意事项

- **API 路径不变**，前端只改 `/wiki/*` → `/ui/*`
- 后端 `/wiki/*` 路由保留兼容（可加 `/<c:.*>` 兜底到 SPA）
- 图谱组件当前用的是 raw HTML + JS，需要评估是否直接保留还是用 G6 React 版
- 基础颜色从 HeroUI `data-theme` 继承，不再需要 `base.css` 的 CSS 变量
