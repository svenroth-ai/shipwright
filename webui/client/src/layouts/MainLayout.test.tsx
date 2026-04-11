import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import { MainLayout } from './MainLayout';

vi.mock('../components/sidebar/SidebarNav', () => ({
  SidebarNav: ({ inboxCount }: { inboxCount: number }) => (
    <nav data-testid="sidebar-nav">Sidebar (inbox: {inboxCount})</nav>
  ),
}));

describe('MainLayout', () => {
  it('renders sidebar and outlet content', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <MainLayout />,
          children: [
            { index: true, element: <div>Page Content</div> },
          ],
        },
      ],
      { initialEntries: ['/'] },
    );

    render(<RouterProvider router={router} />);

    expect(screen.getByTestId('sidebar-nav')).toBeInTheDocument();
    expect(screen.getByText('Page Content')).toBeInTheDocument();
  });
});
