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
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[var(--color-background)]">
        <div className="flex-1 min-h-0 overflow-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
