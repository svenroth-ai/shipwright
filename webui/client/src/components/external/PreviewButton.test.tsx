import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { PreviewButton, previewErrorToToast } from "./PreviewButton";
import { PreviewApiError, ApiError } from "../../lib/externalApi";

describe("PreviewButton", () => {
  it("renders null when enabled = false", () => {
    const { container } = render(
      <PreviewButton projectId="p1" enabled={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the button when enabled = true", () => {
    render(<PreviewButton projectId="p1" enabled />);
    expect(screen.getByTestId("preview-button")).toBeTruthy();
  });
});

describe("previewErrorToToast", () => {
  it("maps preview_spawn_failed", () => {
    const msg = previewErrorToToast(
      new PreviewApiError("preview_spawn_failed", 500, {}),
    );
    expect(msg).toContain("Couldn't start the dev server");
  });

  it("maps preview_port_in_use + interpolates the port", () => {
    const msg = previewErrorToToast(
      new PreviewApiError("preview_port_in_use", 500, { port: 5173 }),
    );
    expect(msg).toContain("Port 5173 is already in use");
  });

  it("maps preview_exited_early", () => {
    const msg = previewErrorToToast(
      new PreviewApiError("preview_exited_early", 500, {}),
    );
    expect(msg).toContain("exited immediately");
  });

  it("maps preview_timeout + interpolates the timeout seconds", () => {
    const msg = previewErrorToToast(
      new PreviewApiError("preview_timeout", 500, { seconds: 60 }),
    );
    expect(msg).toContain("60 s");
  });

  it("maps preview_profile_invalid", () => {
    const msg = previewErrorToToast(
      new PreviewApiError("preview_profile_invalid", 400, {}),
    );
    expect(msg).toContain("Project profile is incomplete");
  });

  it("falls back to a generic message for unknown ApiError codes", () => {
    const msg = previewErrorToToast(
      new ApiError("something_else", 500, { detail: "x" }),
    );
    expect(msg).toContain("Preview failed");
  });

  it("falls back for non-Error inputs", () => {
    expect(previewErrorToToast({ oops: true })).toContain("unknown");
  });
});
