/*
 * useHideIgnored tests — spec § 5.4 "hide-ignored toggle persists per project".
 */

import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useHideIgnored } from "./useHideIgnored";

beforeEach(() => {
  localStorage.clear();
});

describe("useHideIgnored — per-project persistence", () => {
  it("defaults to false when no value stored", () => {
    const { result } = renderHook(() => useHideIgnored("proj-a"));
    expect(result.current[0]).toBe(false);
  });

  it("reads seeded value from localStorage", () => {
    localStorage.setItem("webui.tree.hideIgnored.proj-a", "true");
    const { result } = renderHook(() => useHideIgnored("proj-a"));
    expect(result.current[0]).toBe(true);
  });

  it("set(true) persists + flips state", () => {
    const { result } = renderHook(() => useHideIgnored("proj-a"));
    act(() => {
      result.current[1](true);
    });
    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem("webui.tree.hideIgnored.proj-a")).toBe("true");
  });

  it("keys are per-project — two projects don't collide", () => {
    const { result: a } = renderHook(() => useHideIgnored("proj-a"));
    const { result: b } = renderHook(() => useHideIgnored("proj-b"));
    act(() => {
      a.current[1](true);
    });
    expect(a.current[0]).toBe(true);
    expect(b.current[0]).toBe(false);
    expect(localStorage.getItem("webui.tree.hideIgnored.proj-a")).toBe("true");
    expect(localStorage.getItem("webui.tree.hideIgnored.proj-b")).toBeNull();
  });

  it("re-reads when projectId changes via re-render", () => {
    localStorage.setItem("webui.tree.hideIgnored.proj-b", "true");
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useHideIgnored(id),
      { initialProps: { id: "proj-a" } },
    );
    expect(result.current[0]).toBe(false);
    rerender({ id: "proj-b" });
    expect(result.current[0]).toBe(true);
  });

  it("malformed JSON → default false", () => {
    localStorage.setItem("webui.tree.hideIgnored.proj-a", "{broken");
    const { result } = renderHook(() => useHideIgnored("proj-a"));
    expect(result.current[0]).toBe(false);
  });
});
