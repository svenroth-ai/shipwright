import { useState, useEffect } from 'react';
import { LayoutDashboard, FolderOpen, Inbox, Settings, Menu } from 'lucide-react';
import { SidebarNavItem } from './SidebarNavItem';
import { InboxBadge } from './InboxBadge';

interface SidebarNavProps {
  inboxCount: number;
}

function useMediaCollapse() {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(max-width: 768px)').matches;
  });

  useEffect(() => {
    const mql = window.matchMedia('(max-width: 768px)');
    const handler = (e: MediaQueryListEvent) => setCollapsed(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  return [collapsed, setCollapsed] as const;
}

export function SidebarNav({ inboxCount }: SidebarNavProps) {
  const [collapsed, setCollapsed] = useMediaCollapse();

  return (
    <aside
      className={`${
        collapsed ? 'w-[60px] min-w-[60px]' : 'w-[200px] min-w-[200px]'
      } h-screen bg-white border-r border-gray-200 flex flex-col transition-[width] duration-200`}
    >
      {/* Brand */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-gray-100">
        {collapsed ? (
          <button
            onClick={() => setCollapsed(false)}
            className="p-1 rounded hover:bg-gray-100"
            aria-label="Expand sidebar"
          >
            <Menu size={20} className="text-[var(--color-primary)]" />
          </button>
        ) : (
          <span className="text-base font-semibold text-[var(--color-primary)]">
            Shipwright
          </span>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 flex flex-col gap-1 py-4 px-3">
        <SidebarNavItem
          icon={LayoutDashboard}
          label="Task Board"
          to="/"
          collapsed={collapsed}
        />
        <SidebarNavItem
          icon={FolderOpen}
          label="Projects"
          to="/projects"
          collapsed={collapsed}
        />
        <SidebarNavItem
          icon={Inbox}
          label="Inbox"
          to="/inbox"
          badge={<InboxBadge count={inboxCount} />}
          collapsed={collapsed}
        />
      </nav>

      {/* Bottom: Settings */}
      <div className="border-t border-gray-200 px-3 py-3">
        <SidebarNavItem
          icon={Settings}
          label="Settings"
          to="/settings"
          collapsed={collapsed}
        />
      </div>
    </aside>
  );
}
