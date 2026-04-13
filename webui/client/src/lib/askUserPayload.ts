/**
 * Extract a flat AskUserQuestion payload from the raw tool_input that Claude
 * Code's built-in AskUserQuestion tool emits.
 *
 * The real schema — verified against a live chat-history jsonl dump:
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
 *       }
 *     ]
 *   }
 *
 * (My earlier ADR-015 assumption that `options` lived under `multiSelect`
 *  was wrong — the real shape has them as a sibling, with multiSelect just
 *  being a boolean flag for whether multiple answers are allowed.)
 *
 * This helper flattens both the Claude Code nested shape AND a legacy flat
 * `{ question, context, options }` shape into
 * `{ question, header?, context?, options?, allowMultiple? }` so the client
 * rendering path (AskUserCard) and the server inbox path (index.ts) can use
 * the same extractor.
 */

export interface AskUserPayload {
  question: string;
  context?: string;
  header?: string;
  options?: string[];
  /** Present when the underlying schema marks the question as multi-select */
  allowMultiple?: boolean;
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

export function extractAskUserPayload(toolInput: unknown): AskUserPayload {
  if (!toolInput || typeof toolInput !== 'object') {
    return { question: '' };
  }
  const obj = toolInput as Record<string, unknown>;

  // Claude Code nested schema: { questions: [{ question, header, options: [...], multiSelect: bool }] }
  if (Array.isArray(obj.questions)) {
    const first = obj.questions[0] as Record<string, unknown> | undefined;
    if (!first) return { question: '' };
    const question = typeof first.question === 'string' ? first.question : '';
    const header = typeof first.header === 'string' ? first.header : undefined;
    const options = coerceOptions(first.options);
    const allowMultiple = first.multiSelect === true;
    return { question, header, options, allowMultiple };
  }

  // Legacy flat schema: { question, context, options }
  if (typeof obj.question === 'string') {
    const question = obj.question;
    const context = typeof obj.context === 'string' ? obj.context : undefined;
    const options = coerceOptions(obj.options);
    return { question, context, options };
  }

  return { question: '' };
}
