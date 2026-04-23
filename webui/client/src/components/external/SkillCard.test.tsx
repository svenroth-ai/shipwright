import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SkillCard } from "./SkillCard";

describe("SkillCard — ADR-056 AC-A", () => {
  it("renders the skill name in the header and starts collapsed", () => {
    render(
      <SkillCard
        skillName="Shipwright Compliance Skill"
        body={"# Shipwright Compliance Skill\n\nDetective audit."}
      />,
    );
    const card = screen.getByTestId("skill-card");
    expect(screen.getByTestId("skill-card-name").textContent).toBe(
      "Shipwright Compliance Skill",
    );
    expect(card.querySelector('[data-expanded="false"]')).not.toBeNull();
    expect(screen.queryByTestId("skill-card-body")).toBeNull();
  });

  it("expands to show the markdown-rendered body when the header is clicked", async () => {
    render(
      <SkillCard
        skillName="Compliance"
        body={"# Compliance\n\nSome **bold** text and a list:\n\n- item 1\n- item 2"}
      />,
    );
    await userEvent.click(screen.getByTestId("skill-card-header"));
    const body = screen.getByTestId("skill-card-body");
    // H1 in body
    expect(body.querySelector("h1")?.textContent).toBe("Compliance");
    // bold rendered
    expect(body.querySelector("strong")?.textContent).toBe("bold");
    // list rendered
    expect(body.querySelectorAll("li")).toHaveLength(2);
  });

  it("hides the chevron and disables expansion when body is absent (legacy events)", () => {
    render(<SkillCard skillName="Legacy Skill" />);
    const header = screen.getByTestId("skill-card-header");
    expect(header).toHaveProperty("disabled", true);
    // Body never renders — nothing to expand.
    expect(screen.queryByTestId("skill-card-body")).toBeNull();
  });

  it("renders skill name as plain text (XSS-safe)", () => {
    render(
      <SkillCard
        skillName={"<script>alert(1)</script>"}
        body="# Body long enough to enable expansion"
      />,
    );
    const card = screen.getByTestId("skill-card");
    expect(card.querySelector("script")).toBeNull();
    expect(screen.getByTestId("skill-card-name").textContent).toBe(
      "<script>alert(1)</script>",
    );
  });

  it("neutralizes javascript: URLs in the markdown body (XSS regression)", async () => {
    render(
      <SkillCard
        skillName="Skill"
        body={"# Skill\n\n[bad link](javascript:alert(1))"}
      />,
    );
    await userEvent.click(screen.getByTestId("skill-card-header"));
    const body = screen.getByTestId("skill-card-body");
    const anchor = body.querySelector("a");
    // react-markdown's default sanitizer neutralizes javascript: URLs.
    // The anchor either has no href or href === "" — never an executable
    // `javascript:alert(1)` href.
    expect(anchor).not.toBeNull();
    const href = anchor!.getAttribute("href");
    expect(href).not.toMatch(/^javascript:/i);
  });

  it("keeps its expansion state across parent re-renders (stable instance)", async () => {
    const { rerender } = render(
      <SkillCard skillName="X" body="# X\n\nbody" />,
    );
    await userEvent.click(screen.getByTestId("skill-card-header"));
    expect(screen.getByTestId("skill-card-body")).toBeInTheDocument();
    // Parent re-renders — same props, React preserves instance.
    rerender(<SkillCard skillName="X" body="# X\n\nbody" />);
    expect(screen.getByTestId("skill-card-body")).toBeInTheDocument();
  });
});
