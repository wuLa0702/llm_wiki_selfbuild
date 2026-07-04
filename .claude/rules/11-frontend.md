---
description: LLM Wiki 前端开发规范 — 预留规范，Phase 2/3 启用
globs: frontend/**/*.ts, frontend/**/*.tsx, frontend/**/*.vue
---

# 前端开发规范

> **状态：预留** — 当前 Phase 1 为纯 API 项目，前端后续添加。

## 技术选型（待定）

候选方案（Phase 2 确定）：
- **轻量方案**：FastAPI + Jinja2 模板 + htmx
- **SPA 方案**：React / Vue 3 + Vite

## 代码规范（启用后生效）

- TypeScript，严格模式
- 组件文件使用 PascalCase：`WikiPage.tsx`
- 工具函数使用 camelCase：`formatDate()`
- CSS 使用 Tailwind CSS 或 CSS Modules
- API 调用封装到独立模块，不散落在组件中

## 设计原则

- 移动端优先的响应式设计
- 支持暗色模式
- Wiki 页面渲染支持 Markdown + 双向链接导航
- 页面加载状态、空状态、错误状态都必须覆盖
