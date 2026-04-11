import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { FileExplorer } from './FileExplorer';

function renderExplorer(open = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FileExplorer projectId="proj-1" open={open} onClose={vi.fn()} onFileSelect={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('FileExplorer', () => {
  it('renders when open', () => {
    renderExplorer();
    expect(screen.getByTestId('file-explorer')).toBeInTheDocument();
    expect(screen.getByText('Files')).toBeInTheDocument();
  });

  it('renders nothing when closed', () => {
    renderExplorer(false);
    expect(screen.queryByTestId('file-explorer')).not.toBeInTheDocument();
  });

  it('has filter input', () => {
    renderExplorer();
    expect(screen.getByPlaceholderText('Filter files...')).toBeInTheDocument();
  });
});
