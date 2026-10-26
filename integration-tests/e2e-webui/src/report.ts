// Report folder e2e-report/<timestamp>/: report.md (rendered from report-template.md) plus the images.
// Never receives a token or credential content; callers pass only labels such as the auth source name.
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";

export interface Shooter {
  screenshot(options: { path: string; fullPage?: boolean }): Promise<unknown>;
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
}

export class Report {
  readonly dir: string;
  private steps: StepEntry[] = [];
  private gates: string[] = [];
  private escalations: string[] = [];
  private modelSpend = "not available";
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
    this.dir = path.join(root, this.startedIso.replace(/[:.]/g, "-"));
    fs.mkdirSync(this.dir, { recursive: true });
  }

  /** Records a step; a screenshot failure is noted in the step, never thrown. */
  async step(title: string, shooter: Shooter | null, note = "", extraImages: string[] = []): Promise<string[]> {
    const n = this.steps.length + 1;
    const images = [...extraImages];
    if (shooter) {
      const file = `${String(n).padStart(2, "0")}-${slug(title)}.png`;
      try {
        await shooter.screenshot({ path: path.join(this.dir, file), fullPage: true });
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
      STEPS: this.renderSteps(),
      CHECKLIST: this.checklist.toMarkdown(),
      GATES: list(this.gates, "none"),
      ESCALATIONS: list(this.escalations, "none"),
      MODEL_SPEND: this.modelSpend,
    };
    return this.template.replace(/\{\{([A-Z_]+)\}\}/g, (whole, key: string) => (key in fill ? fill[key] : whole));
  }

  /** Writes report.md; callable repeatedly so a failed or aborted run still leaves a report. */
  write(status: string): string {
    const file = path.join(this.dir, "report.md");
    fs.writeFileSync(file, this.render(status), "utf8");
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
