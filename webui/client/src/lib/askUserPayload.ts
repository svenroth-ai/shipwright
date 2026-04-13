/**
 * Extract a flat AskUserQuestion payload from the raw tool_input that Claude
 * Code's built-in AskUserQuestion tool emits. The real schema is nested:
 *
 *   {
 *     questions: [
 *       {
 *         header: "Priority",
 *         question: "What priority?",
 *         multiSelect: {
 *           mode: "single" | "multi",
 *           options: [{ label: "High", description: "..." }, ...]
 *         }
 *       }
 *     ]
 *   }
 *
 * Older code in this repo assumed a flat `{ question, context, options }`
 * schema, which meant the chat card showed an empty textarea with no question
 * and no option chips. This helper supports both shapes and flattens them
 * into `{ question, context?, options?, header? }` so both the client
 * rendering path (AskUserCard) and the server inbox path (index.ts) can use
 * the same extractor without duplicating shape-sniffing logic.
 */

export interface AskUserPayload {
  question: string;
  context?: string;
  header?: string;
  options?: string[];
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

  // New Claude Code schema: { questions: [{ header, question, multiSelect: { options: [...] } }] }
  if (Array.isArray(obj.questions)) {
    const first = obj.questions[0] as Record<string, unknown> | undefined;
    if (!first) return { question: '' };
    const question = typeof first.question === 'string' ? first.question : '';
    const header = typeof first.header === 'string' ? first.header : undefined;
    const multiSelect = first.multiSelect as { options?: unknown } | undefined;
    const options = multiSelect ? coerceOptions(multiSelect.options) : undefined;
    return { question, header, options };
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
