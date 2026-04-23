import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { SlashCommandChip } from "./SlashCommandChip";

describe("SlashCommandChip", () => {
  it("renders the command name as plain text (no dangerouslySetInnerHTML)", () => {
    render(<SlashCommandChip commandName="/shipwright-compliance:compliance" />);
    const name = screen.getByTestId("slash-command-name");
    expect(name.textContent).toBe("/shipwright-compliance:compliance");
  });

  it("escapes HTML-ish payload — rendered as text, not parsed", () => {
    // If the parser ever slipped, the chip should never execute tags.
    render(<SlashCommandChip commandName={"/<script>alert(1)</script>"} />);
    const chip = screen.getByTestId("slash-command-chip");
    expect(chip.querySelector("script")).toBeNull();
    expect(chip.textContent).toContain("<script>");
  });
});
