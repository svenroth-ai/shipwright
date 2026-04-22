/*
 * MermaidRenderer.test — iterate 3 section 04b.
 *
 * Focuses on the two properties the spec calls out (§ 5.5):
 *  - content-hash memo → identical text does not re-invoke mermaid.
 *  - dispose-before-reinit → switching text empties the host subtree
 *    before the new render is committed (plan § 7 O28).
 *
 * We stub `import("mermaid")` at the module level so the test runs
 * without pulling the ~1.5 MB real library and can spy on `render`.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, screen, act } from "@testing-library/react";

const renderSpy = vi.fn(async (id: string, text: string) => {
  return { svg: `<svg data-id="${id}" data-text="${text.length}"></svg>` };
});
const initSpy = vi.fn();

vi.mock("mermaid", () => ({
  default: {
    initialize: initSpy,
    render: renderSpy,
  },
}));

// Import AFTER the mock so the module resolves to the stub.
import { MermaidRenderer } from "./MermaidRenderer";

beforeEach(() => {
  renderSpy.mockClear();
  initSpy.mockClear();
});

describe("MermaidRenderer — content-hash memo + dispose", () => {
  it("renders an <svg> on first mount", async () => {
    render(<MermaidRenderer text="graph TD; A-->B" />);
    await waitFor(() => {
      expect(renderSpy).toHaveBeenCalledTimes(1);
    });
    const host = screen.getByTestId("smart-viewer-mermaid-svg");
    await waitFor(() => {
      expect(host.querySelector("svg")).toBeTruthy();
    });
  });

  it("same text across re-renders → memo prevents a second render() call", async () => {
    const { rerender } = render(<MermaidRenderer text="graph TD; A-->B" />);
    await waitFor(() => {
      expect(renderSpy).toHaveBeenCalledTimes(1);
    });
    // Rerender with the same text — memo kicks in, renderSpy stays at 1.
    rerender(<MermaidRenderer text="graph TD; A-->B" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(renderSpy).toHaveBeenCalledTimes(1);
  });

  it("different text → re-renders and replaces the previous subtree", async () => {
    const { rerender } = render(<MermaidRenderer text="graph TD; A-->B" />);
    await waitFor(() => {
      expect(renderSpy).toHaveBeenCalledTimes(1);
    });
    rerender(<MermaidRenderer text="graph LR; X-->Y" />);
    await waitFor(() => {
      expect(renderSpy).toHaveBeenCalledTimes(2);
    });
    const host = screen.getByTestId("smart-viewer-mermaid-svg");
    // Exactly one <svg> in the host — the previous render was disposed.
    expect(host.querySelectorAll("svg").length).toBe(1);
    expect(host.querySelector("svg")?.getAttribute("data-text")).toBe(
      String("graph LR; X-->Y".length),
    );
  });

  it("unmount disposes the host subtree", async () => {
    const { unmount } = render(<MermaidRenderer text="graph TD; A-->B" />);
    await waitFor(() => {
      expect(renderSpy).toHaveBeenCalledTimes(1);
    });
    unmount();
    // Host is gone from the DOM — no stranded svg.
    expect(document.querySelector('[data-testid="smart-viewer-mermaid-svg"]')).toBeNull();
  });
});
