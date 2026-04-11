import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useViewerTabs } from './useViewerTabs';

describe('useViewerTabs', () => {
  it('starts with no tabs', () => {
    const { result } = renderHook(() => useViewerTabs());
    expect(result.current.tabs).toHaveLength(0);
    expect(result.current.activeTab).toBeNull();
  });

  it('openTab adds and activates a tab', () => {
    const { result } = renderHook(() => useViewerTabs());
    act(() => result.current.openTab('src/App.tsx', 'proj-1'));

    expect(result.current.tabs).toHaveLength(1);
    expect(result.current.activeTab?.filePath).toBe('src/App.tsx');
    expect(result.current.activeTab?.fileType).toBe('code');
  });

  it('openTab deduplicates by filePath', () => {
    const { result } = renderHook(() => useViewerTabs());
    act(() => result.current.openTab('README.md', 'proj-1'));
    act(() => result.current.openTab('src/App.tsx', 'proj-1'));
    act(() => result.current.openTab('README.md', 'proj-1'));

    expect(result.current.tabs).toHaveLength(2);
    expect(result.current.activeTab?.filePath).toBe('README.md');
  });

  it('closeTab removes tab and activates neighbor', () => {
    const { result } = renderHook(() => useViewerTabs());
    act(() => result.current.openTab('a.md', 'p'));
    act(() => result.current.openTab('b.md', 'p'));
    act(() => result.current.openTab('c.md', 'p'));

    // Active is c.md, close it
    act(() => result.current.closeTab('c.md'));
    expect(result.current.tabs).toHaveLength(2);
    expect(result.current.activeTab?.filePath).toBe('b.md');
  });

  it('closeTab on last tab sets activeTab to null', () => {
    const { result } = renderHook(() => useViewerTabs());
    act(() => result.current.openTab('a.md', 'p'));
    act(() => result.current.closeTab('a.md'));

    expect(result.current.tabs).toHaveLength(0);
    expect(result.current.activeTab).toBeNull();
  });

  it('openUrl creates a url tab', () => {
    const { result } = renderHook(() => useViewerTabs());
    act(() => result.current.openUrl('https://example.com', 'Example', 'p'));

    expect(result.current.activeTab?.fileType).toBe('url');
    expect(result.current.activeTab?.label).toBe('Example');
  });
});
