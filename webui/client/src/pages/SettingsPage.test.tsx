import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SettingsPage from './SettingsPage';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
});

function renderPage(initialEntries: string[] = ['/settings']) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SettingsPage', () => {
  it('renders Settings heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });
  });

  // Iterate 14.8.2 / 14.10 — Global tab renders Default Model + Default Mode dropdowns
  it('Global tab renders Default Model dropdown (defaults to Opus 4.7 in 14.10)', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('default-model-select')).toBeInTheDocument();
    });
    const select = screen.getByTestId('default-model-select') as HTMLSelectElement;
    expect(select.value).toBe('claude-opus-4-7');
  });

  it('Global tab renders Default Permission Mode dropdown (defaults to Auto in 14.10)', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('default-mode-select')).toBeInTheDocument();
    });
    const select = screen.getByTestId('default-mode-select') as HTMLSelectElement;
    expect(select.value).toBe('auto');
  });

  it('Default Permission Mode dropdown includes Auto mode as the first option', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('default-mode-select')).toBeInTheDocument();
    });
    const select = screen.getByTestId('default-mode-select') as HTMLSelectElement;
    expect(select.options[0].value).toBe('auto');
    expect(select.options[0].textContent).toBe('Auto mode');
  });

  it('Default Model dropdown lists Opus 4.7 as the first option', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('default-model-select')).toBeInTheDocument();
    });
    const select = screen.getByTestId('default-model-select') as HTMLSelectElement;
    expect(select.options[0].value).toBe('claude-opus-4-7');
  });

  // Iterate 14.8.2 — Project tab renders color picker
  it('Project tab renders color picker when a project is selected', async () => {
    renderPage(['/settings?tab=project&projectId=proj-1']);
    await waitFor(() => {
      expect(screen.getByTestId('project-color-picker')).toBeInTheDocument();
    });
  });

  // Iterate 14.8.2 — deep-link with ?tab=project activates Project tab
  it('deep-link with ?tab=project activates Project tab', async () => {
    renderPage(['/settings?tab=project&projectId=proj-1']);
    await waitFor(() => {
      expect(screen.getByText('Project Settings')).toBeInTheDocument();
    });
  });

  // Iterate 14.8.2 — deep-link fallback for unknown projectId
  it('falls back to first project when deep-linked projectId is unknown', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    renderPage(['/settings?tab=project&projectId=nonexistent-id']);
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('nonexistent-id'),
      );
    });
    warnSpy.mockRestore();
  });
});
