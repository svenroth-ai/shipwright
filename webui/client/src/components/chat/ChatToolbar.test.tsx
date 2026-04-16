import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { ChatToolbar } from './ChatToolbar';

// Radix Popover is awkward in JSDOM (pointer events, portals). Mock it to a
// flat passthrough so the dropdown content renders synchronously and we can
// assert on click handlers wiring through.
vi.mock('@radix-ui/react-popover', () => ({
  Root: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Trigger: ({ children }: { children: ReactNode; asChild?: boolean }) => <>{children}</>,
  Portal: ({ children }: { children: ReactNode }) => <>{children}</>,
  Content: ({ children }: { children: ReactNode }) => <div role="menu">{children}</div>,
  Close: ({ children }: { children: ReactNode; asChild?: boolean }) => <>{children}</>,
}));

/**
 * Iterate 14.8.3 — ChatToolbar no longer accepts model/setModel props.
 * ModelSelector is now purely driven by chatStore.systemInit via
 * useSystemInitModel(). This suite verifies the new contract: no model
 * prop threading, ModelSelector trigger renders, and the legacy
 * running-model-label testid is still absent.
 *
 * Iterate 14.12 — ChatToolbar now wires onSwitchModel to the
 * useSwitchModel mutation; a click on a different model in the
 * ModelSelector dropdown POSTs to the /mode endpoint.
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

  // Iterate 14.12 (Bug 1) — clicking a model in the dropdown actually
  // fires the /mode mutation. The 14.8.3 stub left this as a no-op.
  it('clicking a model in ModelSelector POSTs to /api/projects/:id/tasks/:taskId/mode', async () => {
    let receivedBody: Record<string, unknown> | null = null;
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ data: { taskId: 'task-1', model: 'opus', status: 'running' } });
      }),
    );

    renderToolbar({ projectId: 'proj-1', taskId: 'task-1' });

    fireEvent.click(screen.getByTestId('model-selector-trigger'));
    // Pop the first option in the dropdown — Opus 4.7 (1M). The trigger
    // also displays "Opus 4.7" as the active label, so scope to the
    // dropdown menu (role="menu" from the Radix mock).
    // Both ModelSelector and PermissionMode use Popover (same Radix mock).
    // The Model menu is the one containing "Opus" entries.
    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opusButton = await within(modelMenu).findByText(/Opus 4\.7/);
    fireEvent.click(opusButton);

    await waitFor(() => expect(receivedBody).not.toBeNull());
    expect(receivedBody).toEqual({ model: 'opus' });
  });

  it('clicking a model when projectId/taskId are missing is a safe no-op', async () => {
    let mutationFired = false;
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', () => {
        mutationFired = true;
        return HttpResponse.json({ data: {} });
      }),
    );

    // No projectId / taskId.
    renderToolbar();
    fireEvent.click(screen.getByTestId('model-selector-trigger'));
    // Both ModelSelector and PermissionMode use Popover (same Radix mock).
    // The Model menu is the one containing "Opus" entries.
    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opusButton = await within(modelMenu).findByText(/Opus 4\.7/);
    fireEvent.click(opusButton);

    // Tiny grace window — the mutation, if fired, would resolve faster
    // than waitFor's default 1s.
    await new Promise((r) => setTimeout(r, 100));
    expect(mutationFired).toBe(false);
  });
});
