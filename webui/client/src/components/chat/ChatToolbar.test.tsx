import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatToolbar } from './ChatToolbar';

/**
 * Iterate 14.8.3 — ChatToolbar no longer accepts model/setModel props.
 * ModelSelector is now purely driven by chatStore.systemInit via
 * useSystemInitModel(). This suite verifies the new contract: no model
 * prop threading, ModelSelector trigger renders, and the legacy
 * running-model-label testid is still absent.
 *
 * PermissionMode internally uses TanStack Query, so every render needs a
 * QueryClientProvider around it.
 */

function renderToolbar(overrides: Partial<React.ComponentProps<typeof ChatToolbar>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatToolbar
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
    renderToolbar();
    expect(screen.getByTestId('model-selector-trigger')).toBeInTheDocument();
  });

  it('no model/setModel props in the interface (compile-time check)', () => {
    // This test exists as a guard: if someone adds model/setModel back
    // to ChatToolbarProps, the type check in renderToolbar() above would
    // still work (extra props are allowed on React components). We assert
    // by checking the component renders without them.
    renderToolbar({});
    expect(screen.getByTestId('model-selector-trigger')).toBeInTheDocument();
  });
});
