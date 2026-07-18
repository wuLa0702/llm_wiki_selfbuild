import { useEffect, useState } from 'react';

interface PageItem {
  path: string;
  title: string;
  page_type: string;
}

interface FileTreeItem {
  name: string;
  type: 'file' | 'directory';
  path?: string;
  size?: number;
  children?: FileTreeItem[];
}

export default function TreePanel({ onSelectPage }: { onSelectPage: (path: string) => void }) {
  const [tab, setTab] = useState<'knowledge' | 'files'>('knowledge');
  const [pages, setPages] = useState<PageItem[]>([]);
  const [fileTree, setFileTree] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set(['/']));
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetch('/v1/pages')
      .then(r => r.json())
      .then(d => setPages(d.pages || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab !== 'files') return;
    fetch('/v1/file-tree')
      .then(r => r.json())
      .then(d => setFileTree(d))
      .catch(() => {});
  }, [tab]);

  const grouped = pages.reduce<Record<string, PageItem[]>>((acc, p) => {
    const t = p.page_type || 'other';
    if (!acc[t]) acc[t] = [];
    acc[t].push(p);
    return acc;
  }, {});

  const typeLabels: Record<string, string> = {
    entity: '实体', concept: '概念', source: '引用源',
    query: '检索问句', comparison: '整合摘要', other: '其他',
  };
  const typeOrder = ['entity', 'concept', 'source', 'comparison', 'query', 'other'];

  const filteredPages = search
    ? pages.filter(p => p.path.includes(search) || p.title.includes(search))
    : pages;

  const toggleDir = (path: string) => {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const renderFileTree = (tree: Record<string, FileTreeItem>, prefix = '') => {
    const entries = Object.entries(tree).sort(([a], [b]) => {
      const aIsDir = tree[a]?.type === 'directory';
      const bIsDir = tree[b]?.type === 'directory';
      if (aIsDir && !bIsDir) return -1;
      if (!aIsDir && bIsDir) return 1;
      return a.localeCompare(b);
    });

    return (
      <ul className="list-none p-0 m-0">
        {entries.map(([name, item]) => {
          const fullPath = prefix ? `${prefix}/${name}` : name;
          if (item.type === 'directory') {
            const isOpen = expandedDirs.has(fullPath);
            return (
              <li key={fullPath}>
                <div
                  className="flex items-center gap-1 px-2 py-1 cursor-pointer text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded"
                  onClick={() => toggleDir(fullPath)}
                >
                  <span className={`text-[0.5rem] transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                  <span>📁</span>
                  <span className="flex-1 truncate">{name}</span>
                </div>
                {isOpen && item.children && (
                  <div className="pl-3">
                    {renderFileTree(item.children, fullPath)}
                  </div>
                )}
              </li>
            );
          }
          return (
            <li key={fullPath}>
              <div
                className="flex items-center gap-1 px-2 py-1 cursor-pointer text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded"
                onClick={() => onSelectPage(fullPath)}
              >
                <span className="w-3">📄</span>
                <span className="flex-1 truncate">{name}</span>
              </div>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <aside className="w-60 flex-shrink-0 bg-gray-50 dark:bg-neutral-900 border-r border-gray-200 dark:border-neutral-700 flex flex-col overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-neutral-700">
        <button
          className={`flex-1 py-2 text-xs font-medium transition-colors ${
            tab === 'knowledge'
              ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-500'
              : 'text-gray-400 dark:text-gray-500 hover:text-gray-600'
          }`}
          onClick={() => setTab('knowledge')}
        >
          知识库
        </button>
        <button
          className={`flex-1 py-2 text-xs font-medium transition-colors ${
            tab === 'files'
              ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-500'
              : 'text-gray-400 dark:text-gray-500 hover:text-gray-600'
          }`}
          onClick={() => setTab('files')}
        >
          文件
        </button>
      </div>

      {/* Search */}
      {tab === 'knowledge' && (
        <div className="px-2 py-2">
          <input
            className="w-full px-2 py-1 text-xs border border-gray-200 dark:border-neutral-700 rounded bg-white dark:bg-neutral-800 outline-none focus:border-blue-400"
            placeholder="搜索页面..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      )}

      {/* Tree content */}
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {tab === 'knowledge' ? (
          loading ? (
            <div className="text-xs text-gray-400 text-center py-4">加载中...</div>
          ) : filteredPages.length === 0 ? (
            <div className="text-xs text-gray-400 text-center py-4">知识库为空</div>
          ) : search ? (
            <ul className="list-none p-0 m-0">
              {filteredPages.map(p => (
                <li key={p.path}>
                  <div
                    className="flex items-center gap-1 px-2 py-1 cursor-pointer text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded"
                    onClick={() => onSelectPage(p.path)}
                  >
                    <span className="w-3">📄</span>
                    <span className="flex-1 truncate">{p.path}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            typeOrder.map(type => {
              const items = grouped[type];
              if (!items?.length) return null;
              return (
                <div key={type} className="mb-1">
                  <div className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                    <span>{typeLabels[type] || type}</span>
                    <span className="text-gray-400 dark:text-gray-500">({items.length})</span>
                  </div>
                  <ul className="list-none p-0 m-0">
                    {items.map(p => (
                      <li key={p.path}>
                        <div
                          className="flex items-center gap-1 px-2 py-1 cursor-pointer text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded ml-2"
                          onClick={() => onSelectPage(p.path)}
                        >
                          <span>{p.title || p.path}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })
          )
        ) : (
          Object.keys(fileTree).length > 0 ? renderFileTree(fileTree) : (
            <div className="text-xs text-gray-400 text-center py-4">暂无文件</div>
          )
        )}
      </div>

      {/* Footer stats */}
      <div className="border-t border-gray-200 dark:border-neutral-700 px-3 py-2 text-[10px] text-gray-400">
        共 {pages.length} 页
      </div>
    </aside>
  );
}
