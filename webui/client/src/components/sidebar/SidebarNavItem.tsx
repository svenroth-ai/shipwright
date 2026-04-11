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
        `flex items-center gap-3 px-3 py-2 rounded-r-lg text-sm border-l-[3px] transition-colors ${
          isActive
            ? 'bg-[var(--color-primary)]/10 border-[var(--color-primary)] active'
            : 'border-transparent hover:bg-gray-100'
        }`
      }
    >
      <Icon
        size={20}
        className="shrink-0"
      />
      <span className={collapsed ? 'sr-only' : 'font-medium text-gray-700 flex-1'}>
        {label}
      </span>
      {badge}
    </NavLink>
  );
}
