# 维基知识库规范（Wiki Schema）

## 页面类型

| 类型 | 存放目录 | 用途说明 |
| ---- | -------- | -------- |
| entity（实体） | wiki/entities/ | 具象命名类条目：人物、工具、机构、数据集等 |
| concept（概念） | wiki/concepts/ | 抽象内容：思路方法、技术、现象、理论框架 |
| source（文献资料） | wiki/sources/ | 论文、期刊文章、讲座、书籍、博客推文 |
| query（待研问题） | wiki/queries/ | 正在调研、尚无定论的开放性问题 |
| comparison（对比分析） | wiki/comparisons/ | 对多个关联实体做并列对照拆解 |
| synthesis（综合综述） | wiki/synthesis/ | 跨条目整合总结、归纳结论 |
| overview（总览） | wiki/ | 项目顶层概要，单个项目仅留存 1 篇总览页 |

## 命名规范

1. **文件统一格式**：短横线分隔命名 `.md`（kebab-case）
2. **实体页**：优先使用官方标准名称，例：`openai.md`、`gpt-4.md`
3. **概念页**：采用描述性名词短语，例：`chain-of-thought.md`（思维链）
4. **资料页**：作者-年份-标识词.md，例：`wei-2022-cot.md`
5. **问题页**：将问句简化为标识词作为文件名，例：`does-scale-improve-reasoning.md`

## 页头元数据（Frontmatter）

所有页面必须在文档开头添加 YAML 前置配置：

```yaml
---
type: entity | concept | source | query | comparison | synthesis | overview
title: 可直接阅读的中文标题
tags: []
related: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### 资料类页面额外必填字段

```yaml
authors: []
year: YYYY
url: ""
venue: ""
```

## 索引页格式

`wiki/index.md` 按页面类型分类汇总全部文档，单条条目写法：

```
- [[page-slug]] — 单行简要说明
```

## 日志页格式

`wiki/log.md` 倒序记录所有编辑与研究动态（最新内容置顶）：

```
## YYYY-MM-DD

- 执行操作 / 记录发现要点
```

## 交叉引用规则

1. 页面间互相跳转统一使用双链语法：`[[页面文件名]]`
2. 所有实体、概念条目必须录入 `wiki/index.md` 索引
3. 调研问题页需关联其参考的资料与概念页面
4. 综合综述页通过 `related:` 字段标注所有参考来源

## 信息冲突处理方案

当多份文献内容存在矛盾时：

1. 在对应概念 / 实体页面中标注该观点冲突
2. 新建或编辑一条待研问题页，用于跟进该争议点
3. 在问题页内双向链接互相矛盾的两份资料
4. 后续证据充分后，在综合综述页完成结论定论
