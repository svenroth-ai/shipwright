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
 *   - Tooltip stays on the caret only.
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21):
 *   - Dropped the per-item description subtitle to tighten the menu width.
 *     Previously the subtitles forced the dropdown to min-width 260px and
 *     still wrapped on narrow viewports. Description text is preserved via
 *     a native `title` attribute on the item so a hovering user still sees
 *     the long form.
 *   - min-width shrunk from 260px → 220px.
 *
 * Regression guard: NO `c` / `Shift+C` binding. Tests assert the absence.
 */

import { useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Tooltip from "@radix-ui/react-tooltip";
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
}

// Per-action visual slot — amber/purple/emerald tiles per mockup
// .new-option-icon.{task,pipeline,iterate} (lines 345–347).
const ACTION_VISUALS: Record<string, ActionVisual> = {
  "new-task": {
    bg: "#FEF3C7", // amber-100
    fg: "#92400E", // amber-800 ≈ --color-warning-text
    icon: CheckSquare,
    kbd: "\u2318 \u21E7 T", // ⌘ ⇧ T
  },
  "new-pipeline": {
    bg: "#F3E8FF", // purple-100 ≈ --color-purple-bg
    fg: "#6B21A8", // purple-800 ≈ --color-purple-text
    icon: Workflow,
    kbd: "\u2318 \u21E7 P",
  },
  "new-iterate": {
    bg: "#D1FAE5", // emerald-100 ≈ --color-success-bg
    fg: "#065F46", // emerald-800 ≈ --color-success-text
    icon: RotateCw,
    kbd: "\u2318 \u21E7 I",
  },
};

const DEFAULT_VISUAL: ActionVisual = {
  bg: "var(--color-muted-bg)",
  fg: "var(--color-muted)",
  icon: Plus,
  kbd: "",
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
        <Tooltip.Provider delayDuration={200}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
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
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                sideOffset={4}
                className="rounded bg-[var(--color-text)] px-2 py-1 text-[11px] text-white shadow"
              >
                Press{" "}
                <kbd className="rounded bg-white/15 px-1 font-mono text-[10px]">
                  i
                </kbd>{" "}
                to open
                <Tooltip.Arrow className="fill-[var(--color-text)]" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            className="z-50 min-w-[220px] rounded-[var(--radius-button)] border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-[var(--shadow-card)]"
            data-testid="create-menu-dropdown"
          >
            {actions.map((a) => {
              const v = ACTION_VISUALS[a.id] ?? DEFAULT_VISUAL;
              const Icon = v.icon;
              return (
                <DropdownMenu.Item
                  key={a.id}
                  data-testid={`create-menu-item-${a.id}`}
                  onSelect={() => onSelect(a)}
                  title={a.description}
                  className="flex cursor-pointer items-center gap-2.5 rounded-[6px] px-2.5 py-2 text-[13px] text-[var(--color-text)] outline-none focus:bg-[var(--color-muted-bg)] hover:bg-[var(--color-muted-bg)]"
                >
                  <span
                    aria-hidden="true"
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px]"
                    style={{ background: v.bg, color: v.fg }}
                  >
                    <Icon size={14} />
                  </span>
                  <span className="flex-1 truncate text-[13px] font-medium leading-tight text-[var(--color-text)]">
                    {a.label}
                  </span>
                  {v.kbd && (
                    <span className="ml-auto shrink-0 rounded-[3px] border border-[var(--color-border)] bg-[var(--color-bg)] px-1.5 py-[1px] font-mono text-[10px] text-[var(--color-muted)]">
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
