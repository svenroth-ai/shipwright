/*
 * Phase badge color map — shared between TaskDetailHeader and TaskCard.
 *
 * 2026-04-23 — iterate-20260423-chat-livetest-2 AC-B.
 *
 * Keys are phase ids from `default-actions.json` (lowercase). The resolver
 * returns a `{ cls, dot }` pair: `cls` is a Tailwind class tuple for the
 * chip background + text color, `dot` is the leading status-dot color.
 *
 * `build` style is the fallback for unknown phase ids — same convention
 * as TaskDetailHeader's pre-extraction inline copy. Keep in sync with
 * the phase color palette in `webui/server/src/config/default-actions.json`.
 */

export interface PhaseStyle {
  cls: string;
  dot: string;
}

const PHASE_STYLES: Record<string, PhaseStyle> = {
  project: { cls: "bg-[var(--color-muted-bg,#ede8e1)] text-[var(--color-muted,#6b7280)]", dot: "bg-[#9ca3af]" },
  design: { cls: "bg-[#F3E8FF] text-[#6B21A8]", dot: "bg-[#A855F7]" },
  plan: { cls: "bg-[#DBEAFE] text-[#1E40AF]", dot: "bg-[#3B82F6]" },
  build: { cls: "bg-[#FEF3C7] text-[#92400E]", dot: "bg-[#F59E0B]" },
  test: { cls: "bg-[#D1FAE5] text-[#065F46]", dot: "bg-[#059669]" },
  deploy: { cls: "bg-[#CCFBF1] text-[#115E59]", dot: "bg-[#14B8A6]" },
  changelog: { cls: "bg-[#E0E7FF] text-[#3730A3]", dot: "bg-[#6366F1]" },
  compliance: { cls: "bg-[#E0F2FE] text-[#075985]", dot: "bg-[#0EA5E9]" },
  security: { cls: "bg-[#FEE2E2] text-[#991B1B]", dot: "bg-[#DC2626]" },
  adopt: { cls: "bg-[#E2E8F0] text-[#334155]", dot: "bg-[#64748B]" },
  iterate: {
    cls: "bg-[var(--color-muted-bg,#ede8e1)] text-[var(--color-muted,#6b7280)]",
    dot: "bg-[var(--color-accent,#857568)]",
  },
};

/**
 * Resolve the color style for a phase id. Unknown ids fall back to the
 * `build` palette to keep the render safe; callers can check whether the
 * input id was known by comparing against `Object.keys(PHASE_STYLES)`.
 */
export function getPhaseStyle(phaseId: string | undefined): PhaseStyle {
  if (!phaseId) return PHASE_STYLES.build;
  return PHASE_STYLES[phaseId.toLowerCase()] ?? PHASE_STYLES.build;
}
