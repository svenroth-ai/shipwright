/*
 * Vitest + React Testing Library coverage for the markdown / code /
 * long-line rendering primitives introduced in 2.2a.
 */

import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MarkdownText } from "./MarkdownText";
import { ToolOutputBlock } from "./ToolOutputBlock";

describe("MarkdownText", () => {
  it("renders inline emphasis + strong without raw markup leaking", () => {
    render(<MarkdownText text={"Hello *world* and **bold** text."} />);
    const body = screen.getByTestId("markdown-body");
    expect(body.querySelector("em")?.textContent).toBe("world");
    expect(body.querySelector("strong")?.textContent).toBe("bold");
    expect(body.textContent).not.toContain("*world*");
  });

  it("renders fenced code with language class for highlight.js", () => {
    const md = "```ts\nconst x: number = 1;\n```";
    render(<MarkdownText text={md} />);
    const code = screen.getByTestId("fenced-code");
    expect(code).toBeInTheDocument();
    expect(code.className).toMatch(/language-ts/);
    expect(code.textContent).toContain("const x: number = 1;");
  });

  it("renders GFM table (remark-gfm extension)", () => {
    const md = `| a | b |\n| - | - |\n| 1 | 2 |\n`;
    render(<MarkdownText text={md} />);
    const body = screen.getByTestId("markdown-body");
    expect(body.querySelector("table")).not.toBeNull();
    expect(within(body).getByText("a")).toBeInTheDocument();
    expect(within(body).getByText("1")).toBeInTheDocument();
  });

  it("opens external links in a new tab with rel=noopener", () => {
    render(<MarkdownText text={"[link](https://example.com)"} />);
    const a = screen.getByRole("link");
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("rel")).toContain("noopener");
  });

  it("does not pass through raw HTML (XSS guard)", () => {
    render(<MarkdownText text={`<script>window.__pwn = true</script><b>safe</b>`} />);
    const body = screen.getByTestId("markdown-body");
    // react-markdown escapes raw HTML by default; tag survives as text, not as <script>.
    expect(body.querySelector("script")).toBeNull();
    expect(body.querySelector("b")).toBeNull();
    expect(body.textContent).toContain("<b>safe</b>");
  });

  it("caps a >200-line code fence with a Show more affordance", async () => {
    const lines = Array.from({ length: 250 }, (_, i) => `line ${i + 1}`).join("\n");
    const md = "```\n" + lines + "\n```";
    render(<MarkdownText text={md} />);

    const code = screen.getByTestId("fenced-code");
    expect(code.textContent).toContain("line 1");
    expect(code.textContent).not.toContain("line 250");

    const showMore = screen.getByTestId("show-more-code");
    expect(showMore.textContent).toMatch(/50 more lines/);

    await userEvent.click(showMore);
    expect(screen.getByTestId("fenced-code").textContent).toContain("line 250");
    expect(screen.getByTestId("show-more-code").textContent).toMatch(/Show less/);
  });

  it("inserts zero-width spaces into lines longer than 2000 chars", () => {
    const longLine = "x".repeat(5000);
    render(<MarkdownText text={longLine} />);
    const body = screen.getByTestId("markdown-body");
    expect(body.textContent).toContain("\u200B");
  });
});

describe("ToolOutputBlock", () => {
  it("strips ANSI escape sequences before rendering", () => {
    const noisy = "\u001b[31mERROR\u001b[0m: thing failed";
    render(<ToolOutputBlock text={noisy} />);
    const block = screen.getByTestId("tool-output-block");
    expect(block.textContent).toBe("ERROR: thing failed");
  });

  it("strips control chars (BEL, FF, BS) but preserves tabs + newlines", () => {
    const text = "a\u0007b\u0008c\u000Cd\te\nf";
    render(<ToolOutputBlock text={text} />);
    const block = screen.getByTestId("tool-output-block");
    expect(block.textContent).toBe("abcd\te\nf");
  });

  it("uses the error variant when is_error is true", () => {
    render(<ToolOutputBlock text="oops" isError />);
    const block = screen.getByTestId("tool-output-block");
    expect(block.dataset.isError).toBe("true");
    // Error variant uses red tokens via inline style (post-iterate-3 LAF sweep).
    // jsdom normalizes the hex palette to rgb() — match either form.
    const background = (block as HTMLElement).style.background;
    const color = (block as HTMLElement).style.color;
    const combined = `${background} ${color}`.toLowerCase();
    const redPattern = /(fef2f2|7f1d1d|red|254,\s*242,\s*242|127,\s*29,\s*29)/;
    expect(combined).toMatch(redPattern);
  });
});
