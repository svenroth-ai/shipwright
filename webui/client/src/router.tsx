import { createBrowserRouter } from 'react-router-dom';
import { MainLayout } from './layouts/MainLayout';
import KanbanPage from './pages/KanbanPage';
import TaskDetailPage from './pages/TaskDetailPage';
import ProjectsPage from './pages/ProjectsPage';
import InboxPage from './pages/InboxPage';
import SettingsPage from './pages/SettingsPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <KanbanPage /> },
      { path: 'tasks/:taskId', element: <TaskDetailPage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);
