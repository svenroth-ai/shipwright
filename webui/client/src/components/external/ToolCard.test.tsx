/*
 * ToolCard unit coverage — 2026-04-23 iterate-20260423-chat-followups AC-1.
 *
 * AC-1 folds tool_result into the matching ToolCard via the new `result`
 * prop. Expanded cards now render both the input (JSON) and the output
 * (via ToolOutputBlock). When `result` is absent the card behaves exactly
 * as it did after iterate-20260423-chat-rendering-polish.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ToolCard } from "./ToolCard";

describe("ToolCard — collapsed-by-default behavior", () => {
  it("renders the name in the title and starts collapsed", () => {
    render(<ToolCard id="tu_1" name="Bash" input={{ command: "ls" }} />);
    const card = screen.getByTestId("tool-card");
    expect(card.dataset.expanded).toBe("false");
    expect(screen.getByTestId("tool-card-title").textContent).toBe("Bash");
    expect(screen.queryByTestId("tool-card-body")).toBeNull();
  });

  it("toggles open when the header is clicked, showing input", async () => {
    render(<ToolCard id="tu_2" name="Read" input={{ file_path: "/tmp/x" }} />);
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const body = screen.getByTestId("tool-card-body");
    expect(body.textContent).toContain("file_path");
    expect(body.textContent).toContain("/tmp/x");
  });
});

describe("ToolCard — AC-1 tool_result folding (expanded body)", () => {
  it("does NOT render output section when result prop is absent", async () => {
    render(<ToolCard id="tu_3" name="Bash" input={{ command: "ls" }} />);
    await userEvent.click(screen.getByTestId("tool-card-header"));
    // Only one body section (input); no output-specific testid present.
    expect(screen.queryByTestId("tool-card-output")).toBeNull();
  });

  it("renders output section when result prop is provided and card is expanded", async () => {
    render(
      <ToolCard
        id="tu_4"
        name="Bash"
        input={{ command: "echo hi" }}
        result={{ content: "hi\n", is_error: false }}
      />,
    );
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const output = screen.getByTestId("tool-card-output");
    expect(output.textContent).toContain("hi");
  });

  it("hides the output section while the card is collapsed", () => {
    render(
      <ToolCard
        id="tu_5"
        name="Bash"
        input={{ command: "echo hi" }}
        result={{ content: "hi\n", is_error: false }}
      />,
    );
    expect(screen.queryByTestId("tool-card-output")).toBeNull();
  });

  it("applies error styling when result.is_error is true", async () => {
    render(
      <ToolCard
        id="tu_6"
        name="Bash"
        input={{ command: "missing" }}
        result={{ content: "command not found", is_error: true }}
      />,
    );
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const output = screen.getByTestId("tool-card-output");
    // ToolOutputBlock carries data-is-error for the error variant.
    expect(output.textContent).toContain("command not found");
    const errBlock = output.querySelector('[data-is-error="true"]');
    expect(errBlock).not.toBeNull();
  });

  it("strips ANSI escapes from the output via ToolOutputBlock", async () => {
    render(
      <ToolCard
        id="tu_7"
        name="Bash"
        input={{ command: "ls --color" }}
        result={{ content: "[31mred[0m file.txt", is_error: false }}
      />,
    );
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const output = screen.getByTestId("tool-card-output");
    expect(output.textContent).toContain("red file.txt");
    expect(output.textContent).not.toMatch(/\[/);
  });

  it("preserves expansion state across rerenders when result arrives later (streaming simulation)", async () => {
    const { rerender } = render(
      <ToolCard id="tu_8" name="Bash" input={{ command: "ls" }} />,
    );
    await userEvent.click(screen.getByTestId("tool-card-header"));
    expect(screen.getByTestId("tool-card").dataset.expanded).toBe("true");

    // Parent passes result on the next polling tick.
    rerender(
      <ToolCard
        id="tu_8"
        name="Bash"
        input={{ command: "ls" }}
        result={{ content: "file.txt\n", is_error: false }}
      />,
    );
    expect(screen.getByTestId("tool-card").dataset.expanded).toBe("true");
    expect(screen.getByTestId("tool-card-output").textContent).toContain("file.txt");
  });
});
