import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import {
  SidebarProvider,
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarFooter,
  SidebarInset,
} from '@/components/ui/sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
  Home, MessageSquare, BookOpen, Search, Activity, FileText,
  Settings, Network, Sparkles,
} from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';
import { useEffect, useState, useMemo, useRef } from 'react';
import { prefetch } from '@/api/client';
import ErrorBoundary from '@/components/shared/ErrorBoundary';

// Pages
import HomePage from '@/pages/HomePage';
import WikiPage from '@/pages/WikiPage';
import ChatPage from '@/pages/ChatPage';
import SearchPage from '@/pages/SearchPage';
import GraphPage from '@/pages/GraphPage';
import SourcesPage from '@/pages/SourcesPage';
import LintPage from '@/pages/LintPage';
import SettingsPage from '@/pages/SettingsPage';
import HealthPage from '@/pages/HealthPage';

const navGroups = [
  {
    label: '导航',
    items: [
      { path: '/home', label: '首页', icon: Home },
      { path: '/chat', label: '对话', icon: MessageSquare },
      { path: '/wiki', label: '知识库', icon: BookOpen },
      { path: '/graph', label: '图谱', icon: Network },
    ],
  },
  {
    label: '工具',
    items: [
      { path: '/sources', label: '原始资料', icon: FileText },
      { path: '/search', label: '检索', icon: Search },
      { path: '/lint', label: 'Wiki 检查', icon: Activity },
    ],
  },
];

/**
 * 一级页面缓存渲染器。
 *
 * 所有路由的页面组件常驻 DOM（display 控制显隐），
 * 切换路由时不 unmount，保留所有 state / ref / 滚动位置 / 网络连接。
 * 首次访问后该页面实例将在 session 期间一直存在。
 */
const CACHEABLE_PAGES = [
  { path: '/home', element: <HomePage /> },
  { path: '/chat', element: <ErrorBoundary name="ChatPage"><ChatPage /></ErrorBoundary> },
  { path: '/wiki', element: <WikiPage /> },
  { path: '/graph', element: <GraphPage /> },
  { path: '/sources', element: <SourcesPage /> },
  { path: '/search', element: <SearchPage /> },
];

function CachedPageHost({ currentPath }: { currentPath: string }) {
  // 记录已访问过的路径，这些页面的 DOM 会被保留
  const [mountedPaths, setMountedPaths] = useState<Set<string>>(() => new Set());

  // 将子路径归一化到父级缓存路径（如 /chat/123 → /chat）
  const parentCachePath = useMemo(() => {
    for (const p of CACHEABLE_PAGES) {
      if (currentPath === p.path) return p.path;
      if (p.path !== '/home' && currentPath.startsWith(p.path + '/')) return p.path;
    }
    return null;
  }, [currentPath]);

  const isCacheablePath = parentCachePath !== null;

  useEffect(() => {
    if (parentCachePath) {
      setMountedPaths(prev => {
        if (prev.has(parentCachePath)) return prev;
        const next = new Set(prev);
        next.add(parentCachePath);
        return next;
      });
    }
  }, [parentCachePath]);

  return (
    <>
      {CACHEABLE_PAGES.map(({ path, element }) => {
        const isActive = currentPath === path ||
          (path !== '/home' && currentPath.startsWith(path + '/'));
        const isMounted = mountedPaths.has(path);
        if (!isMounted && !isActive) return null;
        return (
          <div
            key={path}
            className="flex flex-1 min-h-0 overflow-hidden"
            style={{ display: isActive ? 'flex' : 'none' }}
          >
            {element}
          </div>
        );
      })}
      {/* 非缓存页面：仅在路径匹配时挂载，切换时销毁 */}
      {!isCacheablePath && (
        <Routes>
          <Route path="/settings" element={<Navigate to="/settings/interface" replace />} />
          <Route path="/settings/:tab" element={<SettingsPage />} />
          <Route path="/lint" element={<LintPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="/" element={<Navigate to="/home" replace />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      )}
    </>
  );
}

function AppRoutes() {
  const location = useLocation();
  return <CachedPageHost currentPath={location.pathname} />;
}

export default function App() {
  /* ──────────────────────────────────────────────
     后端就绪检测 — 轮询 /health 直到后端启动完成
     避免在后端预热图谱期间显示散乱的骨架屏
     ────────────────────────────────────────────── */
  const [backendReady, setBackendReady] = useState(false);
  const [startTime] = useState(() => Date.now());
  const warmupRan = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch('/health');
        if (res.ok) {
          if (!cancelled) setBackendReady(true);
          // 后端就绪后启动 prefetch 填满缓存
          if (!warmupRan.current) {
            warmupRan.current = true;
            prefetch(
              '/v1/pages',
              '/v1/pages?sort=created_at&limit=5',
              '/v1/file-tree',
              '/v1/settings',
              '/v1/graph',
              '/v1/sources/tree',
              '/v1/lint?semantic=false',
              '/v1/privacy/rules',
            );
          }
          return;
        }
      } catch {
        // 后端还没起来，继续轮询
      }
      if (!cancelled) setTimeout(check, 500);
    };
    check();
    return () => { cancelled = true; };
  }, []);

  return (
    <BrowserRouter>
      <TooltipProvider>
        <SidebarProvider defaultOpen={true} className="h-svh overflow-hidden">
          <AppSidebar />
          <SidebarInset className="flex flex-col min-h-0 m-2 rounded-xl shadow-sm bg-card overflow-hidden">
            <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
              {backendReady ? <AppRoutes /> : <StartupSplash elapsed={Date.now() - startTime} />}
            </div>
          </SidebarInset>
        </SidebarProvider>
      </TooltipProvider>
    </BrowserRouter>
  );
}

/**
 * 后端启动等待画面 — 仅在后端 HTTP 服务完全就绪前显示
 * 后端预热（图谱构建）已在后台异步执行，不阻塞本画面消失
 */
function StartupSplash({ elapsed }: { elapsed: number }) {
  const [dots, setDots] = useState('');
  useEffect(() => {
    const id = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 500);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.floor(elapsed / 1000);
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
          <Sparkles className="w-8 h-8 text-primary animate-pulse" />
        </div>
        <div className="absolute inset-0 rounded-2xl border-2 border-primary/20 animate-ping opacity-20" />
      </div>
      <div className="text-center space-y-2">
        <p className="text-base font-medium">
          系统启动中{dots}
        </p>
        <p className="text-sm text-muted-foreground">
          正在构建知识图谱和索引，请稍候
        </p>
        {seconds > 2 && (
          <p className="text-xs text-muted-foreground/70 mt-2">
            已等待 {seconds}s
          </p>
        )}
      </div>
      <div className="w-48 h-1 bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full animate-[loading_2s_ease-in-out_infinite]"
             style={{ width: '60%' }} />
      </div>
    </div>
  );
}

function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { resolvedTheme } = useTheme();

  // Apply theme class on mount
  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark');
  }, [resolvedTheme]);

  const isActive = (path: string) => {
    return location.pathname === path ||
      (path !== '/home' && location.pathname.startsWith(path));
  };

  const nav = (path: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    navigate(path);
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<a href="/home" onClick={nav('/home')} className="gap-2" />}>
                <div className="flex items-center justify-center rounded-lg bg-primary text-primary-foreground w-6 h-6">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <span className="font-semibold">LLM Wiki</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

      <SidebarContent>
        {navGroups.map((group, gi) => (
          <SidebarGroup key={gi}>
            {gi > 0 && <div className="sidebar-separator" />}
            <div className="sidebar-group-title">{group.label}</div>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const active = isActive(item.path);
                  return (
                    <SidebarMenuItem key={item.path}>
                      <SidebarMenuButton
                        render={<a href={item.path} onClick={nav(item.path)} />}
                        tooltip={item.label}
                        isActive={active}
                      >
                          <item.icon className="h-4 w-4" />
                          <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              render={<a href="/settings/interface" onClick={nav('/settings/interface')} />}
              tooltip="设置"
            >
                <Settings className="h-4 w-4" />
                <span>设置</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
