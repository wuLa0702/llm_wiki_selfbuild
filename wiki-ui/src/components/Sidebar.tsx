import { NavLink } from 'react-router-dom';

const navItems = [
  { path: '/chat', label: '对话', icon: '💬' },
  { path: '/wiki', label: 'Wiki', icon: '📚' },
  { path: '/wiki/home', label: '原始资料', icon: '📖' },
  { path: '/search', label: '检索', icon: '🔍' },
  { path: '/graph', label: '图谱', icon: '🕸️' },
  { path: '/wiki/audit', label: 'Wiki 检查', icon: '✅' },
];

export default function Sidebar() {
  return (
    <aside
      className="flex-shrink-0 flex flex-col border-r"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)', width: 'fit-content', minWidth: "3.5rem" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-3" style={{ color: 'var(--foreground)' }}>
        <span className="text-xl">📚</span>
        <span className="text-base font-semibold whitespace-nowrap">llm-wiki</span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 px-3 py-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 rounded transition-colors no-underline whitespace-nowrap ${
                isActive ? 'menu-item-active' : ''
              }`
            }
            style={({ isActive }) => ({
              height: "2.625rem",
              fontSize: "var(--fs-md)",
              color: isActive ? 'var(--foreground)' : 'var(--muted)',
              background: isActive ? 'var(--surface-tertiary)' : 'transparent',
              borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
            })}
          >
            <span className="text-lg flex-shrink-0">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Spacer + Settings at bottom */}
      <div className="flex-1" />
      <div className="px-3 border-t flex items-center" style={{ borderColor: 'var(--border)', height: "2.625rem" }}>
        <NavLink
          to="/settings/llm"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 rounded transition-colors no-underline whitespace-nowrap ${
              isActive ? 'menu-item-active' : ''
            }`
          }
          style={({ isActive }) => ({
            height: "2.625rem",
            fontSize: "var(--fs-md)",
            color: isActive ? 'var(--foreground)' : 'var(--muted)',
            background: isActive ? 'var(--surface-tertiary)' : 'transparent',
            borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
          })}
        >
          <span className="text-lg flex-shrink-0">⚙️</span>
          <span>设置</span>
        </NavLink>
      </div>
    </aside>
  );
}
