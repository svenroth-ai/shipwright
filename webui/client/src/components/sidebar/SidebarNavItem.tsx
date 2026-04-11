import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';

interface SidebarNavItemProps {
  icon: LucideIcon;
  label: string;
  to: string;
  badge?: ReactNode;
  collapsed?: boolean;
}

export function SidebarNavItem({ icon: Icon, label, to, badge, collapsed }: SidebarNavItemProps) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        `flex items-center gap-[10px] px-3 py-[9px] rounded-lg text-sm transition-colors ${
          isActive
            ? 'bg-white/[0.12] text-white'
            : 'text-white/70 hover:bg-white/[0.08] hover:text-white'
        }`
      }
    >
      <Icon
        size={18}
        className="shrink-0"
      />
      <span className={collapsed ? 'sr-only' : 'font-medium flex-1'}>
        {label}
      </span>
      {badge}
    </NavLink>
  );
}
