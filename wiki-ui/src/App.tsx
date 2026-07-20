import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useTheme } from '@heroui/react';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import WikiPage from './pages/WikiPage';
import HomePage from './pages/HomePage';
import SearchPage from './pages/SearchPage';
import GraphPage from './pages/GraphPage';
import AuditPage from './pages/AuditPage';
import SettingsPage from './pages/SettingsPage';

import TestCardPage from './pages/TestCardPage';

export default function App() {
  const { setTheme } = useTheme();

  useEffect(() => {
    const saved = localStorage.getItem('ui_theme') || 'dark';
    setTheme(saved);
  }, []);

  useEffect(() => {
    const handler = () => {
      const saved = localStorage.getItem('ui_theme') || 'dark';
      setTheme(saved);
    };
    window.addEventListener('themechange', handler);
    return () => window.removeEventListener('themechange', handler);
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/test-card" element={<TestCardPage />} />
        <Route path="*" element={<MainLayout />} />
      </Routes>
    </BrowserRouter>
  );
}

function MainLayout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: 'var(--background)' }}>
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/wiki" element={<WikiPage />} />
          <Route path="/wiki/home" element={<HomePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/wiki/audit" element={<AuditPage />} />
          <Route path="/settings/:tab" element={<SettingsPage />} />
          <Route path="/settings" element={<Navigate to="/settings/interface" replace />} />
          <Route path="/" element={<Navigate to="/wiki/home" replace />} />
          <Route path="*" element={<Navigate to="/wiki/home" replace />} />
        </Routes>
      </main>
    </div>
  );
}
