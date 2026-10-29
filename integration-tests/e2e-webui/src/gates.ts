// S08: were the gates the spec answered the ones a person would answer, with no unexpected escalation?
// The expected list is written here, apart from the code that answers gates (driver.ts, terminal-gate.ts), so the
// answering code is not graded by its own rules. Matching is by MEANING (finding F7: phrasing varies between
// "Approve screens" and "Approve mockups"), never by exact wording.
import type { Checklist } from "./checklist.js";

export interface ExpectedGate {
  meaning: string;
  pattern: RegExp;
}

export const EXPECTED_GATES: ExpectedGate[] = [
  { meaning: "approve the design (screens, mockups or review)", pattern: /\bapprov(?:e|ed|al)\b/i },
  { meaning: "launch the next pipeline phase", pattern: /launched the next pipeline phase/i },
  { meaning: "submit answers the person has already given", pattern: /^submit/i },
];

/**
 * What a gate is judged by: for a terminal question the OPTION that was chosen, never the question text (a question
 * that merely mentions "approve" must not make an unrelated option look expected); otherwise the recorded text.
 */
export function subject(gate: string): string {
  return /answered with its first option "([^"]+)"/.exec(gate)?.[1] ?? gate;
}

/** Words that mean something went wrong or was waived, in the question or the option: always unexpected. */
const NEVER_EXPECTED = /exemption|safety dialog|dangerous|stop the run|skip|waive|reject|deny|not approved|(?:do not|don'?t|never) approve|disapprov/i;

export interface GateVerdict {
  expected: string[];
  unexpected: string[];
}

export function classifyGates(gates: string[]): GateVerdict {
  const verdict: GateVerdict = { expected: [], unexpected: [] };
  for (const g of gates) {
    // The veto reads the whole text (question and option); the expected meaning is judged on the chosen option only.
    const known = !NEVER_EXPECTED.test(g) && EXPECTED_GATES.some((e) => e.pattern.test(subject(g)));
    (known ? verdict.expected : verdict.unexpected).push(g);
  }
  return verdict;
}

export function checkGates(gates: string[], escalations: string[], checklist: Checklist): void {
  const v = classifyGates(gates);
  const ok = v.unexpected.length === 0 && escalations.length === 0;
  checklist.record("S08", ok ? "pass" : "fail",
    `${v.expected.length} gate(s) answered as expected; unexpected gates: ${v.unexpected.length ? v.unexpected.join(" | ") : "none"}; escalations: ${escalations.length ? escalations.join(" | ") : "none"}`);
}
