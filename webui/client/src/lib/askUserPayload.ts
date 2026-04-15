/**
 * Extract an AskUserQuestion payload from the raw tool_input that Claude
 * Code's built-in AskUserQuestion tool emits.
 *
 * Iterate 14.2: Claude CLI always emits `questions: Array<Question>`, even
 * when there's only one question. Earlier versions of this helper read
 * `questions[0]` and silently dropped parts 2..N — users only saw question 1,
 * Claude then hallucinated answers for the rest. Now we extract ALL questions
 * as parts so the UI can render them as an accordion and submit joins the
 * answers into a single tool_result.
 *
 * The real CLI schema — verified against a live chat-history jsonl dump:
 *
 *   {
 *     questions: [
 *       {
 *         question: "What priority?",
 *         header: "Priority",
 *         options: [                      // <-- DIRECTLY on the question
 *           { label: "High", description: "..." },
 *           { label: "Low", description: "..." }
 *         ],
 *         multiSelect: false              // <-- BOOLEAN, not an object
 *       },
 *       ...
 *     ]
 *   }
 *
 * (My earlier ADR-015 assumption that `options` lived under `multiSelect`
 *  was wrong — the real shape has them as a sibling, with multiSelect just
 *  being a boolean flag for whether multiple answers are allowed.)
 *
 * This helper flattens both the Claude Code nested shape AND a legacy flat
 * `{ question, context, options }` shape into `{ parts: InboxItemPart[] }`
 * so the client rendering path (AskUserCard) and the server inbox path
 * (index.ts) can use the same extractor.
 */

import type { InboxItemPart } from '../types/inbox.js';

export interface AskUserPayload {
  parts: InboxItemPart[];
}

function coerceOptions(raw: unknown): string[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const labels = raw
    .map((opt) => {
      if (typeof opt === 'string') return opt;
      if (opt && typeof opt === 'object' && 'label' in opt && typeof (opt as { label?: unknown }).label === 'string') {
        return (opt as { label: string }).label;
      }
      return null;
    })
    .filter((label): label is string => label !== null && label.length > 0);
  return labels.length > 0 ? labels : undefined;
}

function buildPart(raw: Record<string, unknown>): InboxItemPart {
  const question = typeof raw.question === 'string' ? raw.question : '';
  const header = typeof raw.header === 'string' ? raw.header : undefined;
  const context = typeof raw.context === 'string' ? raw.context : undefined;
  const options = coerceOptions(raw.options);
  const allowMultiple = raw.multiSelect === true || raw.allowMultiple === true ? true : undefined;
  const part: InboxItemPart = { question };
  if (header !== undefined) part.header = header;
  if (context !== undefined) part.context = context;
  if (options !== undefined) part.options = options;
  if (allowMultiple !== undefined) part.allowMultiple = allowMultiple;
  return part;
}

export function extractAskUserPayload(toolInput: unknown): AskUserPayload {
  if (!toolInput || typeof toolInput !== 'object') {
    return { parts: [] };
  }
  const obj = toolInput as Record<string, unknown>;

  // Claude Code nested schema:
  //   { questions: [{ question, header, options: [...], multiSelect: bool }, ...] }
  if (Array.isArray(obj.questions)) {
    const parts: InboxItemPart[] = [];
    for (const entry of obj.questions) {
      if (!entry || typeof entry !== 'object') continue;
      parts.push(buildPart(entry as Record<string, unknown>));
    }
    return { parts };
  }

  // Legacy flat schema: { question, context, options }
  if (typeof obj.question === 'string') {
    return { parts: [buildPart(obj)] };
  }

  return { parts: [] };
}

/**
 * Deterministic serialization of multi-part answers into ONE tool_result
 * string, per the format agreed in the iterate 14 plan:
 *
 *   ## {header or "Question 1"}
 *   {answer verbatim, multiline preserved}
 *
 *   ## {header or "Question 2"}
 *   {answer}
 *
 * Rules:
 * - Missing header → fallback `"Question N"` (1-indexed).
 * - Duplicate headers → suffix ` (1)`, ` (2)` (based on order).
 * - Multi-line answers: preserved verbatim, no code-fence wrapping.
 * - Multi-select answers (passed in as a comma-joined string already, since
 *   the UI collects them that way) stay on one line.
 * - Empty optional answers: still include the header with body `(skipped)`.
 */
export function serializePartAnswers(parts: InboxItemPart[]): string {
  // First pass: compute fallback headers.
  const rawHeaders: string[] = parts.map((p, idx) =>
    p.header && p.header.trim().length > 0 ? p.header.trim() : `Question ${idx + 1}`,
  );

  // Second pass: disambiguate duplicate headers with (1), (2) suffixes.
  const counts = new Map<string, number>();
  for (const h of rawHeaders) counts.set(h, (counts.get(h) ?? 0) + 1);
  const seen = new Map<string, number>();
  const finalHeaders: string[] = rawHeaders.map((h) => {
    const total = counts.get(h) ?? 1;
    if (total <= 1) return h;
    const nth = (seen.get(h) ?? 0) + 1;
    seen.set(h, nth);
    return `${h} (${nth})`;
  });

  const blocks = parts.map((p, idx) => {
    const header = finalHeaders[idx];
    const rawAnswer = typeof p.answer === 'string' ? p.answer : '';
    const body = rawAnswer.length > 0 ? rawAnswer : '(skipped)';
    return `## ${header}\n${body}`;
  });

  return blocks.join('\n\n');
}
