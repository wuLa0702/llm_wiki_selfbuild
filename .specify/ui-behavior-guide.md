# LLM Wiki — UI 行为指导规范

> 版本：2026-07-13 | 适用于所有前端开发，违反即 bug

---

## 一、布局架构

### 1.1 三区模型

```
┌──────────┬──────────────────┬─────────────────────────┐
│ icon-bar │  sidebar-zone     │  main-zone               │
│ 110px    │  260px            │  flex-1                  │
│ (固定)   │  (页面声明)        │  (页面声明)               │
└──────────┴──────────────────┴─────────────────────────┘
```

| 区域 | id | 职责 | 如何定制 |
|------|:--:|------|---------|
| 图标栏 | — | 应用级导航，所有页面统一 | 不可定制，固定 |
| 侧栏区 | `#sidebar-zone` | 页面的导航/辅助面板 | `{% block sidebar_content %}` |
| 主内容区 | `#main-zone` | 页面的核心内容 | `{% block content %}` |

### 1.2 侧栏声明规则

| 页面 | sidebar_content | 说明 |
|------|----------------|------|
| 首页、资料源、图谱、健康 | 默认（tree-sidebar） | 树形面板：知识库 + 文件 |
| 问答 `/wiki/query` | chat-history 面板 | 对话历史列表 |
| 设置 `/wiki/settings` | settings-menu 面板 | 设置二级菜单 |
| 未来页面 | 自定义面板 | 遵循同样的 260px 宽度 |

**规则**：每个页面通过 `{% block sidebar_content %}` 自己声明侧栏内容。不声明 → 默认树形面板。空 → 侧栏隐藏。

### 1.3 导航机制

- 图标栏按钮使用 **htmx**（`hx-get` + `hx-target="#main-zone"` + `hx-push-url`）
- 后台检测 `HX-Request` 头 → 只返回 `{% block content %}` + `{% block scripts %}`
- 同时 `sidebar-zone` 通过 `hx-swap-oob` 替换
- **全页刷新**时走完整模板渲染

---

## 二、颜色系统

### 2.1 变量表

| Token | 亮色 | 暗色 | 用途 |
|-------|------|------|------|
| `--bg-primary` | `#ffffff` | `#18181b` | 主背景 |
| `--bg-surface` | `#f4f4f5` | `#27272a` | 卡片表面 |
| `--bg-sidebar` | `#fafafa` | `#1f1f23` | 图标栏背景 |
| `--bg-tree` | `#f4f4f5` | `#222226` | 树形面板/设置菜单背景 |
| `--bg-hover` | `#e6e6e8` | `#2e2e32` | hover 状态 |
| `--text-primary` | `#18181b` | `#fafafa` | 正文 |
| `--text-secondary` | `#52525b` | `#a1a1aa` | 辅助文字 |
| `--text-muted` | `#a1a1aa` | `#71717a` | 弱化/禁用文字 |
| `--border` | `#e4e4e7` | `rgba(255,255,255,0.06)` | 边框 |
| `--accent-blue` | `#2563eb` | `#3b82f6` | 链接/强调 |
| `--success` | `#16a34a` | 不变 | 成功 |
| `--warning` | `#d97706` | 不变 | 警告 |
| `--error` | `#dc2626` | 不变 | 错误 |

### 2.2 使用规则

- **不要硬编码颜色**。始终使用 CSS 变量。
- 暗色模式切换通过 `<html>` 上的 `.dark` class 控制。
- 页面内嵌 `<style>` 中如需颜色，也用 CSS 变量，不写死 hex。

---

## 三、排版

### 3.1 字号

| 层级 | 大小 | 用途 |
|------|:----:|------|
| h1 | 1.65rem | 页面标题，底部有 border |
| h2 | 1.35rem | 区块标题 |
| h3 | 1.1rem | 子标题 |
| 正文 | 1rem (16px) | body 默认 |
| `.text-sm` | 0.85rem | 辅助文字 |
| `.text-xs` | 0.75rem | 脚注/时间戳 |

### 3.2 间距

| 元素 | 值 |
|------|:--:|
| 主内容区 padding | `2rem 2.5rem 2rem 3rem` |
| 卡片 padding | `1.25rem` |
| 卡片间距 | `1rem` (margin-bottom) |
| 段落间距 | `1em` |
| 圆角 `--radius-md` | 8px |
| 圆角 `--radius-lg` | 10px |

---

## 四、交互行为

### 4.1 加载态 / 空态 / 错误态

**每个数据加载区域必须覆盖三态。**

| 状态 | CSS class | 用法 |
|------|-----------|------|
| 加载中 | `.loading-state` + `.spinner` | 数据请求期间 |
| 为空 | `.empty-state` + `.empty-state-icon` | 无数据时，含引导操作 |
| 错误 | `.error-state` | 请求失败，含重试按钮 |

### 4.2 图谱交互

| 操作 | 行为 |
|------|------|
| 鼠标悬停节点 | 该节点 + 邻居高亮，其余节点变淡；tooltip 显示入链/出链 |
| 离开节点 | 恢复原始色 |
| 单击节点 | 底部弹出详情面板（类型/连接数/社区），非全屏 |
| 双击节点 | 跳转到对应 wiki 页面 |
| 搜索框输入 | 实时过滤，不匹配的节点隐藏 |
| "核心"/"全部"按钮 | 切换 30 节点 / 全节点 |

### 4.3 树形面板

| 操作 | 行为 |
|------|------|
| 点击分组标题 | 展开/折叠，状态存入 **localStorage**（key: `wikiSection_{分组名}`） |
| 点击页面项 | 跳转到对应 wiki 页面 |
| 文件 tab 目录 | 默认展开第 1 级，2 级及以上折叠 |
| 文件 tab .md 点击 | 使用 marked.js 渲染 |
| 图标栏切换页面 | 树形面板不刷新，状态保持 |

### 4.4 问答页

| 操作 | 行为 |
|------|------|
| 输入 + Enter | 发送消息 |
| Shift + Enter | 换行 |
| 对话记录 | localStorage 存储，左侧历史列表 |
| 新建对话 | 创建新会话 |

### 4.5 反馈

- 操作成功/失败 → `showToast()` 底部右下 3 秒提示
- 删除操作 → `confirm()` 二次确认
- 保存操作 → 按钮变 "保存中…" + disabled

---

## 五、技术约束

1. **零构建步骤**：纯 Jinja2 + 原生 CSS + 原生 JS，不引入 webpack/vite
2. **CDN 库**：highlight.js、marked.js、htmx、Sigma.js v3（ESM import map）
3. **无 TypeScript**：所有 JS 为 ES5 兼容语法（`var`、`function`、无箭头函数）
4. **所有新页面模板**：`{% extends "base.html" %}`，声明 `sidebar_content` + `content`
5. **颜色永不硬编码**：始终用 `var(--xxx)` 或 CSS 变量
6. **所有 API 调用**：必须带超时 + 错误处理
7. **文件写入 API**：必须做路径越权校验（`normpath` + 前缀检查）

---

## 六、文件组织

```
src/api/templates/
├── base.html              ← 布局骨架 + htmx 双模式
├── components/
│   ├── icon-sidebar.html  ← 图标栏（所有页面共享）
│   ├── tree-sidebar.html  ← 树形面板（默认侧栏）
│   └── ...                ← 可复用组件
├── wiki/
│   ├── index.html         ← 首页
│   ├── page.html          ← wiki 页面
│   ├── graph.html         ← 图谱（Sigma.js）
│   ├── lint.html          ← 健康检查
│   └── settings.html      ← 设置
├── sources.html           ← 资料源
├── query.html             ← 问答
├── queue.html             ← 队列
└── import.html            ← 导入

static/
├── css/
│   ├── base.css           ← CSS 变量 + 布局 + 排版 + 工具类
│   └── components.css     ← 组件样式
└── js/
    ├── base.js            ← 主题/树形/活动/工具函数
    ├── search.js          ← 搜索下拉
    └── wikilinks.js       ← Wikilink hover
```
