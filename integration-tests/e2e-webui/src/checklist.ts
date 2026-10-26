// expected-result.md items: "- [hard] H01: text" / "- [soft] S01: text". Hard must hold; soft is recorded.
export type Kind = "hard" | "soft";
export type Verdict = "pass" | "fail" | "observed" | "not evaluated";

export interface Item {
  id: string;
  kind: Kind;
  text: string;
  verdict: Verdict;
  evidence: string;
}

const LINE = /^- \[(hard|soft)\] ([A-Z]\d+): (.+)$/;

export function parseChecklist(markdown: string): Item[] {
  const items: Item[] = [];
  for (const raw of markdown.split(/\r?\n/)) {
    const m = LINE.exec(raw.trim());
    if (m) items.push({ id: m[2], kind: m[1] as Kind, text: m[3], verdict: "not evaluated", evidence: "" });
  }
  return items;
}

export class Checklist {
  constructor(readonly items: Item[]) {}

  record(id: string, verdict: Verdict, evidence = ""): void {
    const item = this.items.find((i) => i.id === id);
    if (!item) throw new Error(`Unknown checklist item ${id}`);
    item.verdict = verdict;
    item.evidence = evidence;
  }

  /** Hard items that did not pass (failed or never evaluated). */
  hardOpen(): Item[] {
    return this.items.filter((i) => i.kind === "hard" && i.verdict !== "pass");
  }

  toMarkdown(): string {
    const rows = this.items.map((i) => `| ${i.id} | ${i.kind} | ${cell(i.text)} | ${i.verdict} | ${cell(i.evidence)} |`);
    return ["| Item | Kind | Expectation | Result | Evidence |", "|---|---|---|---|---|", ...rows].join("\n");
  }
}

function cell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}
