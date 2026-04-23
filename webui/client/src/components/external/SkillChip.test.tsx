import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { SkillChip } from "./SkillChip";

describe("SkillChip", () => {
  it("renders the skill name as plain text (no dangerouslySetInnerHTML)", () => {
    render(<SkillChip skillName="Shipwright Compliance Skill" />);
    const name = screen.getByTestId("skill-chip-name");
    expect(name.textContent).toBe("Shipwright Compliance Skill");
  });

  it("renders the 'Skill:' label alongside the name", () => {
    render(<SkillChip skillName="Iterate" />);
    const chip = screen.getByTestId("skill-chip");
    expect(chip.textContent).toContain("Skill:");
    expect(chip.textContent).toContain("Iterate");
  });

  it("escapes HTML-ish payload — rendered as text, not parsed", () => {
    render(<SkillChip skillName={"<script>alert(1)</script>"} />);
    const chip = screen.getByTestId("skill-chip");
    expect(chip.querySelector("script")).toBeNull();
    expect(chip.textContent).toContain("<script>");
  });
});
