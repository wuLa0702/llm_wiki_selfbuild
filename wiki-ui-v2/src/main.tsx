import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { setupGlobalErrorHandlers } from '@/utils/logger';

// 子路径部署：统一给绝对路径的 API 请求加前缀（vite base 注入，生产 '/llm-wiki'）
const API_PREFIX = import.meta.env.BASE_URL.replace(/\/$/, '');
if (API_PREFIX) {
  const origFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === 'string' && (input.startsWith('/v1/') || input === '/health')) {
      input = API_PREFIX + input;
    }
    return origFetch(input, init);
  }) as typeof fetch;
}

// 全局错误捕获：window.onerror / unhandledrejection → 日志上报（不崩页面）
setupGlobalErrorHandlers();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary name="App">
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
