import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { SmartViewer } from './SmartViewer';

function renderViewer() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SmartViewer projectId="proj-1" />
    </QueryClientProvider>,
  );
}

describe('SmartViewer', () => {
  it('shows empty state when no tabs', () => {
    renderViewer();
    expect(screen.getByText('Open a file from the explorer or click a file link')).toBeInTheDocument();
  });

  it('has smart-viewer test id', () => {
    renderViewer();
    expect(screen.getByTestId('smart-viewer')).toBeInTheDocument();
  });
});
