/*
 * `+ New ▾` split-button (iterate 3 section 03 / FR-03.10..14).
 *
 * Layout:
 *   [   + <primary>   ][▾]
 *     └─ primary fires `actions[0]`   └─ caret opens the Radix DropdownMenu
 *
 * Tooltip: caret only. Hovering the primary stays silent so rapid
 * double-clicks remain a fluent path.
 *
 * Global `i` shortcut: registered in TaskBoardPage, NOT here. This
 * component only OWNS the click path; the keyboard handler is the
 * page's problem because it needs to gate on "user isn't typing in an
 * input" and ignore when modals are already open.
 *
 * Regression guard: there is NO `c` / `Shift+C` binding anywhere in
 * this file. Tests assert the explicit absence.
 */

import { useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ChevronDown, Loader2, Plus } from "lucide-react";

import type { ActionDefinition } from "../../lib/externalApi";

interface CreateMenuSplitButtonProps {
  actions: ActionDefinition[];
  /** Fired when primary OR a dropdown item is clicked. */
  onSelect: (action: ActionDefinition) => void;
  /** True while `useProjectActions` is loading. Disables the whole button. */
  isLoading?: boolean;
}

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
      className="inline-flex overflow-hidden rounded border border-[var(--color-primary,#6b5e56)] shadow-sm"
      data-testid="create-menu-split-button"
    >
      <button
        type="button"
        onClick={() => primary && onSelect(primary)}
        disabled={disabled}
        data-testid="create-menu-primary"
        className="inline-flex items-center gap-1.5 border-r border-[var(--color-primary-hover,#5a4f48)] bg-[var(--color-primary,#6b5e56)] px-3 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-[var(--color-primary-hover,#5a4f48)] disabled:cursor-not-allowed disabled:opacity-60"
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
                  className="inline-flex items-center justify-center bg-[var(--color-primary,#6b5e56)] px-2 text-white transition-colors hover:bg-[var(--color-primary-hover,#5a4f48)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <ChevronDown size={14} />
                </button>
              </DropdownMenu.Trigger>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                sideOffset={4}
                className="rounded bg-neutral-900 px-2 py-1 text-[11px] text-white shadow"
              >
                Press <kbd className="rounded bg-white/15 px-1 font-mono text-[10px]">i</kbd> to open
                <Tooltip.Arrow className="fill-neutral-900" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={4}
            className="z-50 min-w-[220px] rounded border border-[var(--color-border,#e0dbd4)] bg-white p-1 shadow-lg"
            data-testid="create-menu-dropdown"
          >
            {actions.map((a) => (
              <DropdownMenu.Item
                key={a.id}
                data-testid={`create-menu-item-${a.id}`}
                onSelect={() => onSelect(a)}
                className="flex cursor-pointer flex-col gap-0.5 rounded px-3 py-2 text-[13px] text-neutral-900 outline-none hover:bg-[var(--color-muted-bg,#ede8e1)] focus:bg-[var(--color-muted-bg,#ede8e1)]"
              >
                <span className="font-medium">{a.label}</span>
                {a.description && (
                  <span className="text-[11px] text-neutral-500">
                    {a.description}
                  </span>
                )}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}
