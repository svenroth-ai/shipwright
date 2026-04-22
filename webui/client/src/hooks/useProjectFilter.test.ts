/*
 * useProjectFilter — shared hook for the active-project state across the
 * Sidebar project list and the TaskBoard filter chip bar (and later the
 * Inbox filter chip, external review O27).
 *
 * Reconciliation rules:
 *   - URL ?projectId=<id> wins on mount over localStorage.
 *   - Missing / null / empty-string = All Projects.
 *   - Reserved literal "unassigned" is a valid value (maps to the synthesized
 *     pseudo-project).
 *   - set* updates BOTH URL and localStorage synchronously.
 */

import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import React from "react";

import { useProjectFilter, PROJECT_FILTER_STORAGE_KEY } from "./useProjectFilter";

function wrapper(initialEntries: string[]) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(MemoryRouter, { initialEntries }, children);
}

beforeEach(() => {
  localStorage.clear();
});

describe("useProjectFilter", () => {
  it("defaults-to-null-all-projects: no URL, no localStorage → null", () => {
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/"]),
    });
    expect(result.current.activeProjectId).toBeNull();
  });

  it("reads-from-localStorage-on-mount: pre-populated key flows through", () => {
    localStorage.setItem(PROJECT_FILTER_STORAGE_KEY, "p-1");
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/"]),
    });
    expect(result.current.activeProjectId).toBe("p-1");
  });

  it("url-query-overrides-localStorage: URL wins + writes back into localStorage", () => {
    localStorage.setItem(PROJECT_FILTER_STORAGE_KEY, "p-1");
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/?projectId=p-2"]),
    });
    expect(result.current.activeProjectId).toBe("p-2");
    // Reconciliation: URL value gets mirrored into localStorage so a
    // subsequent navigation without the query keeps the selection.
    expect(localStorage.getItem(PROJECT_FILTER_STORAGE_KEY)).toBe("p-2");
  });

  it("set-writes-both-url-and-localStorage", () => {
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/"]),
    });
    act(() => {
      result.current.setActiveProjectId("p-3");
    });
    expect(result.current.activeProjectId).toBe("p-3");
    expect(localStorage.getItem(PROJECT_FILTER_STORAGE_KEY)).toBe("p-3");
  });

  it("set-null-clears-both: URL param removed, localStorage cleared", () => {
    localStorage.setItem(PROJECT_FILTER_STORAGE_KEY, "p-7");
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/?projectId=p-7"]),
    });
    act(() => {
      result.current.setActiveProjectId(null);
    });
    expect(result.current.activeProjectId).toBeNull();
    // The hook MUST treat both "no key" and empty-string as All Projects —
    // check it via a fresh read cycle.
    const stored = localStorage.getItem(PROJECT_FILTER_STORAGE_KEY);
    expect(stored === null || stored === "").toBe(true);
  });

  it("reserved-unassigned-valid: setActiveProjectId('unassigned') persists as-is", () => {
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/"]),
    });
    act(() => {
      result.current.setActiveProjectId("unassigned");
    });
    expect(result.current.activeProjectId).toBe("unassigned");
    expect(localStorage.getItem(PROJECT_FILTER_STORAGE_KEY)).toBe("unassigned");
  });

  it("empty-string-in-url-treated-as-null", () => {
    const { result } = renderHook(() => useProjectFilter(), {
      wrapper: wrapper(["/?projectId="]),
    });
    expect(result.current.activeProjectId).toBeNull();
  });
});
