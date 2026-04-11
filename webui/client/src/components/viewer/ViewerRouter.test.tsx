import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { describe, it, expect } from 'vitest';
import { ViewerRouter } from './ViewerRouter';
import type { ViewerTab } from '../../types/viewer';

function renderRouter(tab: ViewerTab) {
  // Mock the docs endpoint for file content
  server.use(
    http.get('/api/projects/:id/docs', () =>
      HttpResponse.json({ data: '# Mock content' }),
    ),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ViewerRouter tab={tab} projectId="proj-1" />
    </QueryClientProvider>,
  );
}

const makeTab = (filePath: string, fileType: ViewerTab['fileType']): ViewerTab => ({
  id: filePath,
  label: filePath.split('/').pop()!,
  filePath,
  fileType,
  projectId: 'proj-1',
});

describe('ViewerRouter', () => {
  it('renders code renderer for code files', async () => {
    renderRouter(makeTab('src/App.tsx', 'code'));
    await waitFor(() => {
      expect(screen.getByTestId('code-renderer')).toBeInTheDocument();
    });
  });

  it('shows link for url type', () => {
    renderRouter(makeTab('https://example.com', 'url'));
    expect(screen.getByText('https://example.com')).toBeInTheDocument();
  });

  it('shows unsupported for unknown type', async () => {
    renderRouter(makeTab('file.xyz', 'unknown'));
    await waitFor(() => {
      expect(screen.getByText('Unsupported file type')).toBeInTheDocument();
    });
  });
});
