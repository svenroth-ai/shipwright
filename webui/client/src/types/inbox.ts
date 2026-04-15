export type InboxStatus = "pending" | "answered";

/**
 * A single question inside an inbox item.
 *
 * Iterate 14.2 — Claude CLI's AskUserQuestion tool always emits a
 * `questions: Array<Question>` payload, sometimes with 2-4 entries in one
 * tool_use call. We store ALL of them as `parts[]` so the user sees every
 * question and we can join their answers into one deterministic tool_result.
 */
export interface InboxItemPart {
  question: string;
  header?: string;
  context?: string;
  /** Label-only option list (descriptions stripped at extraction time). */
  options?: string[];
  allowMultiple?: boolean;
  /** Undefined until the user has answered this specific part. */
  answer?: string;
  answeredAt?: string;
}

/**
 * An inbox item corresponds to exactly ONE AskUserQuestion tool_use call
 * from Claude CLI. When Claude asks multiple questions at once, each one
 * becomes a part inside the same item.
 */
export interface InboxItem {
  /** Claude's `tool_use_id` (e.g. `toolu_...`) or a random UUID fallback. */
  id: string;
  projectId: string;
  taskId: string;
  parts: InboxItemPart[];
  status: InboxStatus;
  createdAt: string;
  /** Set only when ALL parts have been answered. */
  answeredAt?: string;
  /**
   * Iterate 14.5 — true when Claude continued generating (text or further
   * tool_use blocks) after this AskUserQuestion without waiting for the
   * user's answer, OR when the turn ended before any `tool_result` matched
   * this tool_use. Drives the amber "Claude did not wait" warning banner
   * in AskUserCard. Persisted to inbox.jsonl so the flag survives refresh.
   */
  notBlocked?: boolean;
}
