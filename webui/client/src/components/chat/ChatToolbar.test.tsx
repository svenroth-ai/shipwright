import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatToolbar } from './ChatToolbar';

/**
 * Iterate 14.7.1 — the separate running-model label added in 14.6 was
 * folded into ModelSelector. This suite pins the inverted assertion
 * (the `running-model-label` testid must NOT render) plus sanity checks
 * on the other toolbar controls.
 *
 * PermissionMode internally uses TanStack Query, so every render needs a
 * QueryClientProvider around it.
 */

function renderToolbar(overrides: Partial<React.ComponentProps<typeof ChatToolbar>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatToolbar
        model="sonnet"
        setModel={vi.fn()}
        mode="bypassPermissions"
        setMode={vi.fn()}
        autonomy="guided"
        {...overrides}
      />
    </QueryClientProvider>,
  );
}

describe('ChatToolbar', () => {
  it('does NOT render the legacy running-model-label testid', () => {
    renderToolbar();
    expect(screen.queryByTestId('running-model-label')).toBeNull();
  });

  it('renders the ModelSelector trigger', () => {
    renderToolbar({ model: 'opus' });
    expect(screen.getByTestId('model-selector-trigger')).toBeInTheDocument();
  });
});
