import { useState, useEffect } from 'react';
import { LayoutDashboard, FolderOpen, Inbox, Settings, Menu, Activity } from 'lucide-react';
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
      } h-screen bg-[var(--color-sidebar-bg)] flex flex-col transition-[width] duration-200`}
    >
      {/* Brand */}
      <div className="flex items-center gap-2 px-4 py-5 pb-6">
        {collapsed ? (
          <button
            onClick={() => setCollapsed(false)}
            className="p-1 rounded hover:bg-white/10"
            aria-label="Expand sidebar"
          >
            <Menu size={20} className="text-white" />
          </button>
        ) : (
          <>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 text-white shrink-0">
              <circle cx="12" cy="12" r="8"/>
              <circle cx="12" cy="12" r="2.5"/>
              <line x1="12" y1="2" x2="12" y2="9.5"/>
              <line x1="12" y1="14.5" x2="12" y2="22"/>
              <line x1="2" y1="12" x2="9.5" y2="12"/>
              <line x1="14.5" y1="12" x2="22" y2="12"/>
              <line x1="4.93" y1="4.93" x2="9.17" y2="9.17"/>
              <line x1="14.83" y1="14.83" x2="19.07" y2="19.07"/>
              <line x1="4.93" y1="19.07" x2="9.17" y2="14.83"/>
              <line x1="14.83" y1="9.17" x2="19.07" y2="4.93"/>
            </svg>
            <span className="text-base font-bold text-white">
              Shipwright
            </span>
          </>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex flex-col gap-1 py-2 px-3">
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
        <SidebarNavItem
          icon={Activity}
          label="Diagnostics"
          to="/diagnostics"
          collapsed={collapsed}
        />
      </nav>

      {/* Spacer — pushes Settings to the bottom. Phase B1 removed the
          project list from the sidebar; the TaskBoard header dropdown is
          now the single source of truth for project selection. */}
      <div className="flex-1" />

      {/* Bottom: Settings */}
      <div className="border-t border-white/10 px-3 py-3">
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
