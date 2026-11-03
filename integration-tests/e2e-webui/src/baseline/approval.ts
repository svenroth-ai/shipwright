// The Brief package in the repo is kept exactly as delivered (its hash is protected). Approval is not part of the hash, so the
// harness records it the way the other fixtures carry it, `approved_by: "fixture:<name>"`, but in the run's COPY of the package
// (`<project>/brief/brief.json`), and only when the delivered package has none. The pipeline accepts a fixture approval only with
// SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL=1, which the run sets.
import fs from "node:fs";
import path from "node:path";

export const BASELINE_APPROVER = "fixture:social-engagement-baseline";

/** Stamps approved_by / approved_at into `<copy>/brief.json` when absent. Returns true when it wrote. Never touches the source package. */
export function recordFixtureApproval(copyDir: string, approver: string = BASELINE_APPROVER, now: Date = new Date()): boolean {
  const file = path.join(copyDir, "brief.json");
  const brief = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
  if (typeof brief.approved_by === "string" && brief.approved_by !== "") return false;
  const { package_sha256: hash, ...rest } = brief; // keep the hash last, as the other fixtures do
  fs.writeFileSync(file, `${JSON.stringify({ ...rest, approved_by: approver, approved_at: now.toISOString().replace(/\.\d+Z$/, "Z"), package_sha256: hash }, null, 2)}\n`);
  return true;
}
