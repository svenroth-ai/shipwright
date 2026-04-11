import { createBrowserRouter } from 'react-router-dom';
import { MainLayout } from './layouts/MainLayout';
import KanbanPage from './pages/KanbanPage';
import TaskDetailPage from './pages/TaskDetailPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <KanbanPage /> },
      { path: 'tasks/:taskId', element: <TaskDetailPage /> },
      { path: 'projects', element: <div className="p-6"><h1 className="text-2xl font-semibold text-gray-900">Projects</h1></div> },
      { path: 'inbox', element: <div className="p-6"><h1 className="text-2xl font-semibold text-gray-900">Inbox</h1></div> },
      { path: 'settings', element: <div className="p-6"><h1 className="text-2xl font-semibold text-gray-900">Settings</h1></div> },
    ],
  },
]);
