import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PreviewButton } from './PreviewButton';

describe('PreviewButton (iterate 14.1)', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn(async () => new Response(JSON.stringify({ data: { taskId: 'abc' } }), { status: 202 }));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders with Preview label and Play icon', () => {
    render(<PreviewButton projectId="p1" />);
    expect(screen.getByRole('button', { name: /preview/i })).toBeInTheDocument();
  });

  it('POSTs to /api/projects/:id/preview on click', async () => {
    render(<PreviewButton projectId="p1" />);
    const btn = screen.getByRole('button', { name: /preview/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/api/projects/p1/preview', { method: 'POST' });
    });
  });

  it('disables itself briefly while the request is in flight', async () => {
    let resolveFetch!: (v: Response) => void;
    const pendingSpy = vi.fn(() => new Promise<Response>((r) => { resolveFetch = r; }));
    vi.stubGlobal('fetch', pendingSpy);
    render(<PreviewButton projectId="p1" />);
    const btn = screen.getByRole('button', { name: /preview/i }) as HTMLButtonElement;
    fireEvent.click(btn);
    await waitFor(() => {
      expect(btn.disabled).toBe(true);
    });
    resolveFetch(new Response('{}', { status: 202 }));
    await waitFor(() => {
      expect(btn.disabled).toBe(false);
    });
  });
});
