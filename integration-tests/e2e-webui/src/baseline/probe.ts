// A Probe collects the small expectations one checklist item is made of and turns them into one verdict with
// readable evidence. A failed expectation never throws, so one item reports every broken rule, not only the first.
export class Probe {
  private passed = 0;
  private failed: string[] = [];
  private notes: string[] = [];

  /** One expectation. `label` is a plain phrase ("a second start reuses the process"); `detail` is shown only on failure. */
  expect(label: string, ok: boolean, detail = ""): boolean {
    if (ok) this.passed += 1;
    else this.failed.push(detail ? `${label} (${detail})` : label);
    return ok;
  }

  /** Deep-equal on JSON-able values. */
  equal(label: string, actual: unknown, expected: unknown): boolean {
    const sorted = (v: unknown): unknown => (Array.isArray(v) ? v.map(sorted) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).sort(([x], [y]) => (x < y ? -1 : 1)).map(([k, x]) => [k, sorted(x)])) : v);
    const a = JSON.stringify(sorted(actual));
    const e = JSON.stringify(sorted(expected));
    return this.expect(label, a === e, `got ${clip(a)}, wanted ${clip(e)}`);
  }

  /** Information that is not an expectation (which form of a command was used, ...). */
  note(text: string): void {
    this.notes.push(text);
  }

  get ok(): boolean {
    return this.failed.length === 0 && this.passed > 0;
  }

  verdict(): { pass: boolean; evidence: string } {
    const head = this.failed.length === 0 && this.passed > 0 ? `${this.passed} expectations hold` : `${this.passed} hold, ${this.failed.length} broken: ${this.failed.slice(0, 6).join("; ")}${this.failed.length > 6 ? `; and ${this.failed.length - 6} more` : ""}`;
    return { pass: this.failed.length === 0 && this.passed > 0, evidence: [head, ...this.notes].join(". ") };
  }
}

export const clip = (s: string, n = 140): string => (s.length > n ? `${s.slice(0, n)}...` : s);
