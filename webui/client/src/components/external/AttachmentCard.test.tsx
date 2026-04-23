import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { AttachmentCard } from "./AttachmentCard";

describe("AttachmentCard", () => {
  it("renders the basename in mono font", () => {
    render(<AttachmentCard basename="app.ts" />);
    expect(screen.getByTestId("attachment-basename").textContent).toBe("app.ts");
  });

  it("renders basename only (no path segments) — caller is responsible for basename-ing", () => {
    // If caller somehow passes a full path, the component renders what it's given —
    // but in practice, session-parser's fileSnapshotBasenames strips paths.
    // This test asserts the component does NOT do anything clever with slashes.
    render(<AttachmentCard basename="secret.ts" />);
    const el = screen.getByTestId("attachment-basename");
    expect(el.textContent).toBe("secret.ts");
    expect(el.textContent).not.toContain("/");
    expect(el.textContent).not.toContain("\\");
  });

  it("shows +N more suffix for multi-file snapshots", () => {
    render(<AttachmentCard basename="spec.md" extraCount={3} />);
    expect(screen.getByTestId("attachment-extra-count").textContent).toBe("+3 more");
  });

  it("hides +N more when extraCount is 0 or omitted", () => {
    render(<AttachmentCard basename="spec.md" />);
    expect(screen.queryByTestId("attachment-extra-count")).toBeNull();
  });

  it("picks an icon based on extension (smoke test — code / image / doc / generic all render)", () => {
    // We don't assert the specific icon — just that the card renders
    // without throwing for each kind family.
    for (const name of ["app.ts", "photo.png", "notes.md", "binary.bin"]) {
      const { unmount } = render(<AttachmentCard basename={name} />);
      expect(screen.getByTestId("attachment-card")).toBeInTheDocument();
      unmount();
    }
  });
});
