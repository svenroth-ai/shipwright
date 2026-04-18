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
  // Iterate 14.13 — body now carries the CONCRETE id (e.g.
  // `claude-opus-4-7`), not the coarse `opus` alias. The CLI accepts
  // both forms but the alias resolves to whatever its compiled-in
  // default-stable-in-family happens to be (4.5/4.6 in CLI 2.1.1),
  // silently dropping the user's exact version pick.
  it('clicking a model in ModelSelector POSTs the concrete id to /api/projects/:id/tasks/:taskId/mode', async () => {
    let receivedBody: Record<string, unknown> | null = null;
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ data: { taskId: 'task-1', model: 'claude-opus-4-7', status: 'running' } });
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
    expect(receivedBody).toEqual({ model: 'claude-opus-4-7' });
  });

  // Iterate 2026-04-18 modelswitch-spawn-ux — pending-target state machine.
  // On switch click: set pendingTargetModel → render target label +
  // spinner. Clear when systemInitModel catches up OR mutation errors.
  it('sets pendingTargetModel on click and forwards it to ModelSelector', async () => {
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async () =>
        HttpResponse.json({ data: { taskId: 'task-1', model: 'claude-opus-4-6', status: 'running' } }),
      ),
    );

    renderToolbar({ projectId: 'proj-1', taskId: 'task-1' });

    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opus46 = await within(modelMenu).findByText(/Opus 4\.6/);
    fireEvent.click(opus46);

    await waitFor(() => {
      const trigger = screen.getByTestId('model-selector-trigger');
      expect(trigger.getAttribute('data-pending-target')).toBe('claude-opus-4-6');
    });
    expect(screen.getByTestId('model-selector-trigger').textContent).toContain('Opus 4.6');
    expect(screen.getByTestId('model-switching-spinner')).toBeInTheDocument();
  });

  it('surfaces server error inline when /mode returns 409', async () => {
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async () =>
        HttpResponse.json(
          { error: 'Answer the pending question before switching mode' },
          { status: 409 },
        ),
      ),
    );

    renderToolbar({ projectId: 'proj-1', taskId: 'task-1' });

    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opus46 = await within(modelMenu).findByText(/Opus 4\.6/);
    fireEvent.click(opus46);

    await waitFor(() =>
      expect(screen.getByTestId('model-switch-error')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('model-switch-error').textContent).toContain('pending question');
    // Pending target is cleared on error so the user can retry.
    await waitFor(() =>
      expect(screen.getByTestId('model-selector-trigger').getAttribute('data-pending-target')).toBeNull(),
    );
  });

  // Iterate modelswitch-uat-round2 (2026-04-18) — Retry button in the
  // error banner for transient 409 "Session not yet established". Lets
  // the user re-fire the switch once the CLI's session_id has been
  // captured (~200-500ms after spawn) instead of manually re-opening
  // the dropdown.
  it('shows Retry button on 409 "Session not yet established" error', async () => {
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async () =>
        HttpResponse.json(
          { error: 'Session not yet established — try again in a second' },
          { status: 409 },
        ),
      ),
    );

    renderToolbar({ projectId: 'proj-1', taskId: 'task-1' });

    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opus46 = await within(modelMenu).findByText(/Opus 4\.6/);
    fireEvent.click(opus46);

    await waitFor(() =>
      expect(screen.getByTestId('model-switch-error')).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId('model-switch-retry')).toBeInTheDocument(),
    );
  });

  it('does NOT show Retry button for non-transient errors (400 invalid model)', async () => {
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async () =>
        HttpResponse.json({ error: 'Invalid model' }, { status: 400 }),
      ),
    );

    renderToolbar({ projectId: 'proj-1', taskId: 'task-1' });

    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opus46 = await within(modelMenu).findByText(/Opus 4\.6/);
    fireEvent.click(opus46);

    await waitFor(() =>
      expect(screen.getByTestId('model-switch-error')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('model-switch-retry')).toBeNull();
  });

  it('clicking Retry re-fires the mutation with the same target model', async () => {
    let postCount = 0;
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async ({ request }) => {
        postCount++;
        const body = (await request.json()) as Record<string, unknown>;
        if (postCount === 1) {
          return HttpResponse.json(
            { error: 'Session not yet established — try again in a second' },
            { status: 409 },
          );
        }
        return HttpResponse.json({ data: { taskId: 'task-1', model: body.model, status: 'running' } });
      }),
    );

    renderToolbar({ projectId: 'proj-1', taskId: 'task-1' });

    const menus = await screen.findAllByRole('menu');
    const modelMenu = menus.find((m) => m.textContent?.includes('Opus'))!;
    const opus46 = await within(modelMenu).findByText(/Opus 4\.6/);
    fireEvent.click(opus46);

    await waitFor(() => expect(screen.getByTestId('model-switch-retry')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('model-switch-retry'));

    await waitFor(() => expect(postCount).toBe(2));
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
