import { useEffect, useState, useCallback } from 'react';
import { createRoot } from 'react-dom/client';

export function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  root.render(<ToastMsg message={message} type={type} onDone={() => { root.unmount(); el.remove(); }} />);
}

function ToastMsg({ message, type, onDone }: { message: string; type: string; onDone: () => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(true);
    const t1 = setTimeout(() => setVisible(false), 2500);
    const t2 = setTimeout(onDone, 2800);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const colors = {
    success: 'bg-green-500',
    error: 'bg-red-500',
    info: 'bg-gray-700 dark:bg-neutral-600',
  };

  return (
    <div
      className={`fixed bottom-4 right-4 z-50 px-3 py-2 rounded-lg text-white text-xs shadow-lg transition-all duration-300 ${
        (colors as any)[type] || colors.info
      } ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}`}
    >
      {message}
    </div>
  );
}
