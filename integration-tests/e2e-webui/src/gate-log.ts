// Gates and escalations are written to the run folder as they happen, so a resumed run judges S08 on the WHOLE
// run (an earlier unexpected gate must still fail it) and not only on what the resumed part saw.
import fs from "node:fs";
import path from "node:path";

export const GATE_LOG = "gates.jsonl";

export type RecordKind = "gate" | "escalation";

export function appendRecord(runDir: string, kind: RecordKind, text: string, now: Date = new Date()): void {
  fs.appendFileSync(path.join(runDir, GATE_LOG), `${JSON.stringify({ kind, text, at: now.toISOString() })}\n`, { mode: 0o600 });
}

/**
 * S08 evidence: what the earlier part left on disk when this run STARTED, plus what this run recorded in memory.
 * The file is not re-read at the end: the agent under test can reach the run folder.
 */
export function wholeRun(earlier: { gates: string[]; escalations: string[] }, gates: string[], escalations: string[]): { gates: string[]; escalations: string[] } {
  return { gates: [...earlier.gates, ...gates], escalations: [...earlier.escalations, ...escalations] };
}

/** Every gate and escalation of the run so far; a line that cannot be read counts as an escalation (fail closed). */
export function loadRecords(runDir: string): { gates: string[]; escalations: string[] } {
  const out = { gates: [] as string[], escalations: [] as string[] };
  const file = path.join(runDir, GATE_LOG);
  if (!fs.existsSync(file)) return out;
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    if (line.trim() === "") continue;
    try {
      const r = JSON.parse(line) as { kind?: string; text?: unknown };
      if (typeof r.text === "string" && r.kind === "gate") out.gates.push(r.text);
      else if (typeof r.text === "string" && r.kind === "escalation") out.escalations.push(r.text);
      else out.escalations.push("an unreadable record in gates.jsonl");
    } catch {
      out.escalations.push("an unreadable record in gates.jsonl");
    }
  }
  return out;
}
