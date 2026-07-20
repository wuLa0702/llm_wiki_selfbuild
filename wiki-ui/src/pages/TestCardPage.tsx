import { Card, CardHeader, CardContent, Chip, Link, Button, Tooltip } from '@heroui/react';

const mockSourceFile = 'raw/sources/_test_batch/very-very-very-very-very-very-very-long-source-file-path-that-should-be-truncated.md';
const mockTags = ['docker', 'devops', 'tool', 'testing'];
const mockLinks = ['concepts/异步编程.md', 'concepts/容器化部署.md', 'sources/Docker官方文档.md'];
const mockBacklinks = ['entities/Docker Compose.md', 'concepts/MCP协议.md'];

export default function TestCardPage() {
  return (
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: 'var(--background)' }}>
      {/* Isolated card test — sidebar and midpanel intentionally omitted */}
      <div className="flex-1 flex flex-col p-8 max-w-4xl mx-auto">
        <h2 className="text-lg font-semibold mb-6 text-default-500">🧪 Card 组件孤立测试</h2>

        {/* Case 1: full data (links + backlinks + source + tags) — bordered variant */}
        <Card variant="default" className="mb-8">
          <CardHeader className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2">
                <Chip size="sm" variant="flat" color="primary">实体</Chip>
                <h1 className="text-base font-semibold">Python</h1>
              </div>
              <div className="flex items-center gap-2 flex-wrap text-xs text-default-500">
                <span>创建 2026-07-18</span>
                {mockTags.map(t => <Chip key={t} size="sm" variant="flat">{t}</Chip>)}
              </div>
            </div>
            <div className="flex gap-1 flex-shrink-0">
              <Button size="sm" variant="ghost">编辑</Button>
              <Button size="sm" variant="ghost">✕</Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-default-400 font-medium mb-0.5">📂 来源溯源</p>
              <Tooltip content={mockSourceFile} delay={300}>
                <p className="text-xs text-default-500 truncate cursor-default">{mockSourceFile}</p>
              </Tooltip>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-default-400 font-medium flex-shrink-0">🔗 正向引用 ({mockLinks.length})</span>
                {mockLinks.map(l => (
                  <Link key={l} size="sm" className="text-xs cursor-pointer">
                    {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                  </Link>
                ))}
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-default-400 font-medium flex-shrink-0">🔙 反向引用 ({mockBacklinks.length})</span>
                {mockBacklinks.map(l => (
                  <Link key={l} size="sm" className="text-xs cursor-pointer">
                    {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                  </Link>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Case 2: minimal data (no source, no tags, no backlinks) — bordered variant */}
        <Card variant="default" className="mb-8">
          <CardHeader className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2">
                <Chip size="sm" variant="flat" color="secondary">概念</Chip>
                <h1 className="text-base font-semibold">异步编程</h1>
              </div>
              <div className="flex items-center gap-2 flex-wrap text-xs text-default-500">
                <span>创建 2026-07-18</span>
              </div>
            </div>
            <div className="flex gap-1 flex-shrink-0">
              <Button size="sm" variant="ghost">编辑</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-1 flex-wrap">
              <span className="text-xs text-default-400 font-medium flex-shrink-0">🔗 正向引用 (0)</span>
              <span className="text-xs text-default-300">无</span>
            </div>
          </CardContent>
        </Card>

        {/* Layout diagnostic info */}
        <div className="mt-4 p-4 rounded-lg text-xs font-mono text-default-400" style={{ background: 'var(--surface)' }}>
          <p className="mb-1 font-semibold">诊断信息：</p>
          <p>• Card variant: bordered（HeroUI 边框可见）</p>
          <p>• CardHeader / CardContent：v2 独立组件（非 compound 模式）</p>
          <p>• 左侧无 Sidebar / MidPanel</p>
          <p>• 纯孤立测试，无页面布局干扰</p>
        </div>
      </div>
    </div>
  );
}
