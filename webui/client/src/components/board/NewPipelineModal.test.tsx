import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { NewPipelineModal } from './NewPipelineModal';

beforeEach(() => {
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.scrollIntoView) {
    HTMLElement.prototype.scrollIntoView = () => undefined;
  }
});

function renderModal(onOpenChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <NewPipelineModal open onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    ),
    onOpenChange,
  };
}

describe('NewPipelineModal', () => {
  it('renders three form fields and the Create button', async () => {
    server.use(
      http.get('/api/profiles', () =>
        HttpResponse.json({ data: [{ name: 'supabase-nextjs', label: 'Supabase + Next.js' }] }),
      ),
    );
    renderModal();
    expect(screen.getByLabelText(/project name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/project path/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/stack profile/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create pipeline/i })).toBeInTheDocument();
  });

  it('loads profiles from /api/profiles into the dropdown', async () => {
    server.use(
      http.get('/api/profiles', () =>
        HttpResponse.json({ data: [
          { name: 'supabase-nextjs', label: 'Supabase + Next.js' },
          { name: 'fastapi', label: 'FastAPI' },
        ] }),
      ),
    );
    renderModal();
    await waitFor(() => {
      const select = screen.getByLabelText(/stack profile/i) as HTMLSelectElement;
      const options = Array.from(select.options).map((o) => o.value);
      expect(options).toContain('supabase-nextjs');
      expect(options).toContain('fastapi');
    });
  });

  it('submits to /api/projects/pipeline and closes on success', async () => {
    server.use(
      http.get('/api/profiles', () =>
        HttpResponse.json({ data: [{ name: 'supabase-nextjs', label: 'Supabase + Next.js' }] }),
      ),
      http.post('/api/projects/pipeline', () =>
        HttpResponse.json({ data: { projectId: 'p-new', taskId: 't-new' } }, { status: 202 }),
      ),
    );
    const { onOpenChange } = renderModal();
    await waitFor(() => {
      expect((screen.getByLabelText(/stack profile/i) as HTMLSelectElement).value).toBe('supabase-nextjs');
    });
    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: 'My App' } });
    fireEvent.change(screen.getByLabelText(/project path/i), { target: { value: '/tmp/my-app' } });
    fireEvent.click(screen.getByRole('button', { name: /create pipeline/i }));
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('iterate 14.7.1 — Paste button reads clipboard and fills the path field', async () => {
    server.use(
      http.get('/api/profiles', () =>
        HttpResponse.json({ data: [{ name: 'supabase-nextjs', label: 'Supabase + Next.js' }] }),
      ),
    );
    const readText = vi.fn().mockResolvedValue('C:\\Users\\sven\\pasted-path');
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: { readText },
    });

    renderModal();
    await waitFor(() => {
      expect((screen.getByLabelText(/stack profile/i) as HTMLSelectElement).value).toBe('supabase-nextjs');
    });

    const pasteBtn = screen.getByTestId('pipeline-path-paste');
    fireEvent.click(pasteBtn);
    await waitFor(() => {
      expect((screen.getByLabelText(/project path/i) as HTMLInputElement).value).toBe(
        'C:\\Users\\sven\\pasted-path',
      );
    });
    expect(readText).toHaveBeenCalled();
  });

  it('iterate 14.7.1 — Paste button shows hint when clipboard is not a path', async () => {
    server.use(
      http.get('/api/profiles', () =>
        HttpResponse.json({ data: [{ name: 'supabase-nextjs', label: 'Supabase + Next.js' }] }),
      ),
    );
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: { readText: vi.fn().mockResolvedValue('hello world') },
    });

    renderModal();
    await waitFor(() => {
      expect((screen.getByLabelText(/stack profile/i) as HTMLSelectElement).value).toBe('supabase-nextjs');
    });

    fireEvent.click(screen.getByTestId('pipeline-path-paste'));
    await waitFor(() => {
      expect(screen.getByText(/Clipboard doesn't look like a path/i)).toBeInTheDocument();
    });
  });

  it('shows inline error on 409 duplicate', async () => {
    server.use(
      http.get('/api/profiles', () =>
        HttpResponse.json({ data: [{ name: 'supabase-nextjs', label: 'Supabase + Next.js' }] }),
      ),
      http.post('/api/projects/pipeline', () =>
        HttpResponse.json({ error: 'project already registered for this path' }, { status: 409 }),
      ),
    );
    renderModal();
    await waitFor(() => {
      expect((screen.getByLabelText(/stack profile/i) as HTMLSelectElement).value).toBe('supabase-nextjs');
    });
    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: 'Dup' } });
    fireEvent.change(screen.getByLabelText(/project path/i), { target: { value: '/tmp/dup' } });
    fireEvent.click(screen.getByRole('button', { name: /create pipeline/i }));
    await waitFor(() => {
      expect(screen.getByText(/already registered/i)).toBeInTheDocument();
    });
  });
});
