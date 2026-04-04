# shadcn/ui Rules for Implementation

> Extracted from the official shadcn/ui skill.
> Source: github.com/shadcn-ui/ui/skills/shadcn/rules/
> Upstream commit: 720ccca65343
> Last synced: 2026-04-05
> Stability: stable (core patterns rarely change)

These rules are **mandatory** when implementing UI with shadcn/ui + Tailwind.
The section-builder must follow Core Rules always. Load category sections only when relevant.

---

## Core Rules (always apply)

### Styling

- **Semantic colors only.** `bg-primary`, `text-muted-foreground` — never raw values like `bg-blue-500`.
- **`gap-*` not `space-y-*` / `space-x-*`.** Use `flex flex-col gap-4` instead of `space-y-4`.
- **`size-*` when width = height.** `size-10` not `w-10 h-10`.
- **`className` for layout only.** `max-w-md`, `mx-auto`, `mt-4` — never override component colors or typography.
- **Built-in variants first.** `variant="outline"` not manual `border border-input bg-transparent`.
- **`cn()` for conditional classes.** Never manual template literal ternaries.
- **No `dark:` overrides.** Semantic tokens handle light/dark via CSS variables.
- **`truncate` shorthand.** Not `overflow-hidden text-ellipsis whitespace-nowrap`.
- **No manual `z-index` on overlays.** Dialog, Sheet, Popover handle their own stacking.

### Composition

- **Full Card composition.** Always use `CardHeader` + `CardTitle` + `CardDescription` + `CardContent` + `CardFooter` + `CardAction`. Never dump everything in `CardContent`.
- **Items always inside their Group.** `SelectItem` → `SelectGroup`. `DropdownMenuItem` → `DropdownMenuGroup`. `CommandItem` → `CommandGroup`.
- **Dialog/Sheet/Drawer need a Title.** `DialogTitle`, `SheetTitle`, `DrawerTitle` required (use `sr-only` if visually hidden).
- **`TabsTrigger` inside `TabsList`.** Never render triggers directly in `Tabs`.
- **`Avatar` needs `AvatarFallback`.** Always include fallback for failed image loads.
- **Use existing components, not custom markup:**

| Instead of | Use |
|---|---|
| Custom callout div | `Alert` + `AlertTitle` + `AlertDescription` |
| Custom empty state div | `Empty` + `EmptyHeader` + `EmptyMedia` + `EmptyTitle` |
| `toast()` custom | `sonner` — `toast.success()`, `toast.error()` |
| `<hr>` or `border-t` div | `Separator` |
| `animate-pulse` div | `Skeleton` |
| Custom styled span | `Badge variant="..."` |

### Forms (always apply when implementing forms)

- **`FieldGroup` + `Field` + `FieldLabel`.** Never raw `div` with `Label`.
- **`InputGroup` + `InputGroupInput`** for buttons inside inputs. Never raw `Input` inside `InputGroup`.
- **`ToggleGroup`** for 2–7 options. Never loop `Button` with manual active state.
- **`FieldSet` + `FieldLegend`** for grouping related checkboxes/radios.
- **Validation:** `data-invalid` on `Field`, `aria-invalid` on the control.

---

## Icons (load when implementing buttons with icons)

- **`data-icon="inline-start"` or `"inline-end"`** on icons inside `Button`.
- **No sizing classes on icons in components.** Components handle icon sizing via CSS.
- **Pass icons as objects** (`icon={CheckIcon}`), not string lookups.

## Overlays (load when implementing modals, sheets, drawers)

| Use case | Component |
|----------|-----------|
| Focused task requiring input | `Dialog` |
| Destructive action confirmation | `AlertDialog` |
| Side panel with details/filters | `Sheet` |
| Mobile-first bottom panel | `Drawer` |
| Quick info on hover | `HoverCard` |
| Small contextual content on click | `Popover` |

## Component Selection (load when choosing which component to use)

| Need | Use |
|------|-----|
| Button/action | `Button` with variant |
| Form inputs | `Input`, `Select`, `Combobox`, `Switch`, `Checkbox`, `RadioGroup`, `Textarea`, `InputOTP`, `Slider` |
| Toggle 2–5 options | `ToggleGroup` + `ToggleGroupItem` |
| Data display | `Table`, `Card`, `Badge`, `Avatar` |
| Navigation | `Sidebar`, `NavigationMenu`, `Breadcrumb`, `Tabs`, `Pagination` |
| Overlays | `Dialog`, `Sheet`, `Drawer`, `AlertDialog` |
| Feedback | `sonner` (toast), `Alert`, `Progress`, `Skeleton`, `Spinner` |
| Command palette | `Command` inside `Dialog` |
| Charts | `Chart` (wraps Recharts) |
| Layout | `Card`, `Separator`, `Resizable`, `ScrollArea`, `Accordion`, `Collapsible` |
| Empty states | `Empty` |
| Menus | `DropdownMenu`, `ContextMenu`, `Menubar` |
| Tooltips/info | `Tooltip`, `HoverCard`, `Popover` |
