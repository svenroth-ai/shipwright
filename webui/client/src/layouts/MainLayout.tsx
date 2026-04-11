import { Outlet } from 'react-router-dom';
import { SidebarNav } from '../components/sidebar/SidebarNav';

export function MainLayout() {
  // TODO: Replace with useInbox() hook from Section 03
  const inboxCount = 0;

  return (
    <div className="flex h-screen overflow-hidden">
      <SidebarNav inboxCount={inboxCount} />
      <main className="flex-1 overflow-auto bg-[var(--color-background)]">
        <Outlet />
      </main>
    </div>
  );
}
