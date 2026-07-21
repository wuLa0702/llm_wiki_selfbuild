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
import { useEffect } from 'react';

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

export default function App() {

  return (
    <BrowserRouter>
      <TooltipProvider>
        <SidebarProvider defaultOpen={true}>
          <AppSidebar />
          <SidebarInset className="flex flex-col min-h-0 m-2 rounded-xl shadow-sm bg-card overflow-hidden">
            <Routes>
              <Route path="/home" element={<HomePage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/wiki" element={<WikiPage />} />
              <Route path="/sources" element={<SourcesPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/graph" element={<GraphPage />} />
              <Route path="/lint" element={<LintPage />} />
              <Route path="/settings" element={<Navigate to="/settings/interface" replace />} />
              <Route path="/settings/:tab" element={<SettingsPage />} />
              <Route path="/health" element={<HealthPage />} />
              <Route path="/" element={<Navigate to="/home" replace />} />
              <Route path="*" element={<Navigate to="/home" replace />} />
            </Routes>
          </SidebarInset>
        </SidebarProvider>
      </TooltipProvider>
    </BrowserRouter>
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
