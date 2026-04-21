/*
 * `+ New ▾` split-button (iterate 3 section 03 / FR-03.10..14; restyled in
 * remediation Phase B1 against `webui/designs/screens/kanban-with-projects.html`
 * lines 270–376).
 *
 * Layout:
 *   [   + <primary>   ][▾]
 *     └─ primary fires `actions[0]`   └─ caret opens the Radix DropdownMenu
 *
 * Phase B1 restyle:
 *   - Primary bg = --color-primary, caret bg = --color-primary-hover
 *     (visually distinct caret per mockup .new-split-caret).
 *   - Dropdown items: 28×28 rounded icon tile (amber/purple/emerald per
 *     action id) + label (500) + kbd shortcut (mono badge). Icon palette
 *     is data-driven off the action id, not the `kind`, so the visual slot
 *     matches the design without widening the ActionDefinition type.
 *
 * Iterate 3.7d-b1 (2026-04-22):
 *   - Re-introduced the per-item descriptive subtitle under the primary
 *     label (matches mockup lines 926–950 — "Standalone task", "Full SDLC",
 *     "Lightweight change"). dropdown widens back to 280px.
 *   - Removed the `i`-shortcut Tooltip from the caret — Sven's UAT feedback
 *     was that keyboard-shortcut tooltips on the caret are noise. The
 *     shortcut still works globally (hooked up in TaskBoardPage).
 *   - Subtitle text is purely descriptive — NOT wired to any shortcut.
 *
 * Regression guard: NO `c` / `Shift+C` binding. Tests assert the absence.
 */

import { useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  ChevronDown,
  CheckSquare,
  Loader2,
  Plus,
  RotateCw,
  Workflow,
} from "lucide-react";

import type { ActionDefinition } from "../../lib/externalApi";

interface CreateMenuSplitButtonProps {
  actions: ActionDefinition[];
  /** Fired when primary OR a dropdown item is clicked. */
  onSelect: (action: ActionDefinition) => void;
  /** True while `useProjectActions` is loading. Disables the whole button. */
  isLoading?: boolean;
}

interface ActionVisual {
  bg: string;
  fg: string;
  icon: React.ComponentType<{ size?: number }>;
  kbd: string;
  subtitle: string;
}

// Per-action visual slot — amber/purple/emerald tiles per mockup
// .new-option-icon.{task,pipeline,iterate} (lines 345–347).
//
// Subtitle copy locked per kanban-with-projects.html mockup lines 926-950:
//   - new-task:     "Standalone task — no pipeline, no copy-command."
//   - new-pipeline: "Full SDLC from brief to deploy."
//   - new-iterate:  "Lightweight change on a finished project."
// We trimmed the mockup's code-literal hints ("Generates claude /shipwright-run …")
// since those leak implementation into a UI tooltip. The trimmed forms still
// carry the same semantic distinctions (standalone vs. pipeline vs. iterate).
const ACTION_VISUALS: Record<string, ActionVisual> = {
  "new-task": {
    bg: "#FEF3C7", // amber-100
    fg: "#92400E", // amber-800 ≈ --color-warning-text
    icon: CheckSquare,
    kbd: "\u2318 \u21E7 T", // ⌘ ⇧ T
    subtitle: "Quick ad-hoc session — no pipeline, no copy-command.",
  },
  "new-pipeline": {
    bg: "#F3E8FF", // purple-100 ≈ --color-purple-bg
    fg: "#6B21A8", // purple-800 ≈ --color-purple-text
    icon: Workflow,
    kbd: "\u2318 \u21E7 P",
    subtitle: "Full SDLC from brief to deploy.",
  },
  "new-iterate": {
    bg: "#D1FAE5", // emerald-100 ≈ --color-success-bg
    fg: "#065F46", // emerald-800 ≈ --color-success-text
    icon: RotateCw,
    kbd: "\u2318 \u21E7 I",
    subtitle: "Lightweight change on a finished project.",
  },
};

const DEFAULT_VISUAL: ActionVisual = {
  bg: "var(--color-muted-bg)",
  fg: "var(--color-muted)",
  icon: Plus,
  kbd: "",
  subtitle: "",
};

export function CreateMenuSplitButton({
  actions,
  onSelect,
  isLoading = false,
}: CreateMenuSplitButtonProps) {
  const [open, setOpen] = useState(false);

  const primary = actions[0];
  const disabled = isLoading || !primary;

  return (
    <div
      className="inline-flex overflow-hidden rounded-[var(--radius-button)] border-[1.5px] border-[var(--color-primary)] shadow-sm"
      data-testid="create-menu-split-button"
    >
      <button
        type="button"
        onClick={() => primary && onSelect(primary)}
        disabled={disabled}
        data-testid="create-menu-primary"
        className="inline-flex items-center gap-1.5 border-r-[1.5px] border-[var(--color-primary-hover)] bg-[var(--color-primary)] px-3 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-[var(--color-primary-hover)] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLoading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
        <span>{primary?.label ?? "New"}</span>
      </button>
      <DropdownMenu.Root open={open} onOpenChange={setOpen}>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            disabled={disabled}
            data-testid="create-menu-caret"
            aria-label="More create options"
            className="inline-flex items-center justify-center bg-[var(--color-primary-hover)] px-2 text-white transition-colors hover:bg-[#443a34] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <ChevronDown size={12} />
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            className="z-50 min-w-[280px] rounded-[var(--radius-button)] border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-[var(--shadow-card)]"
            data-testid="create-menu-dropdown"
          >
            {actions.map((a) => {
              const v = ACTION_VISUALS[a.id] ?? DEFAULT_VISUAL;
              const Icon = v.icon;
              // Subtitle: prefer the mockup-locked copy; fall back to whatever
              // the server-provided action description is (keeps custom
              // .webui/actions.json configurations usable).
              const subtitle = v.subtitle || a.description || "";
              return (
                <DropdownMenu.Item
                  key={a.id}
                  data-testid={`create-menu-item-${a.id}`}
                  onSelect={() => onSelect(a)}
                  className="flex cursor-pointer items-center gap-2.5 rounded-[6px] px-2.5 py-2 text-[13px] text-[var(--color-text)] outline-none focus:bg-[var(--color-muted-bg)] hover:bg-[var(--color-muted-bg)]"
                >
                  <span
                    aria-hidden="true"
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px]"
                    style={{ background: v.bg, color: v.fg }}
                  >
                    <Icon size={14} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span
                      className="truncate text-[13px] font-medium leading-tight text-[var(--color-text)]"
                      data-testid={`create-menu-item-label-${a.id}`}
                    >
                      {a.label}
                    </span>
                    {subtitle && (
                      <span
                        className="truncate text-[11px] leading-[1.35] text-[var(--color-muted)]"
                        data-testid={`create-menu-item-subtitle-${a.id}`}
                      >
                        {subtitle}
                      </span>
                    )}
                  </span>
                  {v.kbd && (
                    <span className="ml-auto shrink-0 self-start rounded-[3px] border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 py-[1px] font-mono text-[10px] text-[var(--color-muted)]">
                      {v.kbd}
                    </span>
                  )}
                </DropdownMenu.Item>
              );
            })}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}
