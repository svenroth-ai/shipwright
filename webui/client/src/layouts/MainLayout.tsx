import { Outlet } from 'react-router-dom';
import { SidebarNav } from '../components/sidebar/SidebarNav';
import { useSSE } from '../hooks/useSSE';
import { useInboxCount } from '../hooks/useInbox';

export function MainLayout() {
  useSSE();
  const inboxCount = useInboxCount();

  return (
    <div className="flex h-screen overflow-hidden">
      <SidebarNav inboxCount={inboxCount} />
      <main className="flex-1 overflow-auto bg-[var(--color-background)]">
        <Outlet />
      </main>
    </div>
  );
}
