import { createBrowserRouter } from 'react-router-dom';
import { MainLayout } from './layouts/MainLayout';
import TaskBoardPage from './pages/TaskBoardPage';
import TaskDetailPage from './pages/TaskDetailPage';
import ProjectsPage from './pages/ProjectsPage';
import InboxPage from './pages/InboxPage';
import SettingsPage from './pages/SettingsPage';
import DiagnosticsPage from './pages/DiagnosticsPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <TaskBoardPage /> },
      { path: 'tasks/:taskId', element: <TaskDetailPage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'diagnostics', element: <DiagnosticsPage /> },
    ],
  },
]);
