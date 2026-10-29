// Report folder e2e-report/<timestamp>/: report.md (rendered from report-template.md) plus the images.
// Never receives a token or credential content; callers pass only labels such as the auth source name.
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";

export interface Shooter {
  screenshot(options: { path: string; fullPage?: boolean; timeout?: number }): Promise<unknown>;
}

interface StepEntry {
  n: number;
  title: string;
  note: string;
  images: string[];
  at: number;
}

export interface ReportMeta {
  config: Record<string, string>;
  authSource: string;
  /** git HEAD of the checkout whose plugins the run loads, with a dirty-tree flag (E8 records the commit under test). */
  commit?: string;
}

export class Report {
  readonly dir: string;
  private steps: StepEntry[] = [];
  private gates: string[] = [];
  private escalations: string[] = [];
  private modelSpend = "not available";
  private screenshotCheck = "not recorded";
  private resume = "new run (not resumed)";
  private readonly started = Date.now();
  private readonly startedIso: string;

  constructor(
    root: string,
    private readonly meta: ReportMeta,
    private readonly checklist: Checklist,
    private readonly template: string,
    now: Date = new Date(),
  ) {
    this.startedIso = now.toISOString();
    // The folder name is the timestamp plus a random suffix (mkdtemp), so it cannot be guessed or pre-created.
    fs.mkdirSync(root, { recursive: true, mode: 0o700 });
    this.dir = fs.mkdtempSync(path.join(root, `${this.startedIso.replace(/[:.]/g, "-")}-`));
  }

  /** Records a step; a screenshot failure is noted in the step, never thrown. */
  async step(title: string, shooter: Shooter | null, note = "", extraImages: string[] = []): Promise<string[]> {
    const n = this.steps.length + 1;
    const images = [...extraImages];
    if (shooter) {
      const file = `${String(n).padStart(2, "0")}-${slug(title)}.png`;
      try {
        await shooter.screenshot({ path: path.join(this.dir, file), fullPage: true, timeout: 30_000 });
        images.push(file);
      } catch (error) {
        note = `${note} (screenshot failed: ${(error as Error).message})`.trim();
      }
    }
    this.steps.push({ n, title, note, images, at: Date.now() });
    return images;
  }

  gate(text: string): void {
    this.gates.push(text);
  }
  escalation(text: string): void {
    this.escalations.push(text);
  }
  setScreenshotCheck(text: string): void {
    this.screenshotCheck = text;
  }
  setResume(text: string): void {
    this.resume = text;
  }
  gateList(): string[] {
    return [...this.gates];
  }
  escalationList(): string[] {
    return [...this.escalations];
  }
  setModelSpend(text: string): void {
    this.modelSpend = text;
  }

  render(status: string, now: number = Date.now()): string {
    const fill: Record<string, string> = {
      STATUS: status,
      STARTED: this.startedIso,
      DURATION: minutes(now - this.started),
      CONFIG: Object.entries(this.meta.config).map(([k, v]) => `- ${k}: ${v}`).join("\n"),
      AUTH_SOURCE: this.meta.authSource,
      PLUGIN_COMMIT: this.meta.commit ?? "not recorded",
      RESUME: this.resume,
      STEPS: this.renderSteps(),
      CHECKLIST: this.checklist.toMarkdown(),
      GATES: list(this.gates, "none"),
      ESCALATIONS: list(this.escalations, "none"),
      SCREENSHOT_CHECK: this.screenshotCheck,
      MODEL_SPEND: this.modelSpend,
    };
    return this.template.replace(/\{\{([A-Z_]+)\}\}/g, (whole, key: string) => (key in fill ? fill[key] : whole));
  }

  /** Writes report.md; callable repeatedly so a failed or aborted run still leaves a report. */
  write(status: string): string {
    const file = path.join(this.dir, "report.md");
    fs.writeFileSync(file, this.render(status), { encoding: "utf8", mode: 0o600 });
    return file;
  }

  private renderSteps(): string {
    if (this.steps.length === 0) return "_no steps ran_";
    return this.steps
      .map((s) => {
        const lines = [`### ${s.n}. ${s.title}`, `Elapsed: ${minutes(s.at - this.started)}`];
        if (s.note) lines.push("", s.note);
        for (const img of s.images) lines.push("", `![${s.title}](${img})`);
        return lines.join("\n");
      })
      .join("\n\n");
  }
}

function list(items: string[], empty: string): string {
  return items.length === 0 ? empty : items.map((i) => `- ${i}`).join("\n");
}
function minutes(ms: number): string {
  return `${(ms / 60000).toFixed(1)} min`;
}
export function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "step";
}
