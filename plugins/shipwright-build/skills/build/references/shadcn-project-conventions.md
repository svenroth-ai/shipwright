# shadcn/ui Project Conventions (Shipwright Enhancement)

> Production-tested patterns from real Shipwright projects.
> NOT from upstream shadcn/ui — custom conventions based on production experience.
> Complements `shadcn-rules.md` (upstream) with project-level styling guidance.

---

## Card Variants

When mixing image-cards (flush top image) and content-only cards in the same layout:

- **Image-Cards:** `overflow-hidden border-0 !pt-0` — image fills card top edge
- **Content-Cards:** Standard `py-6` padding from Card base component
- **Skeleton loaders** must match exact dimensions of the real card (same height, same border-radius)
- **Card grids:** Use a consistent grid pattern across all card views:
  ```
  gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4
  ```

## Disabled Button Styling

`disabled:opacity-50` alone makes buttons nearly invisible on light backgrounds. Use explicit muted styling:

```tsx
// Correct: visible but clearly inactive
className="disabled:bg-muted disabled:text-muted-foreground disabled:opacity-60"
```

Minimum widths per button size to prevent layout shift:
- `default` → `min-w-[100px]`
- `sm` → `min-w-[80px]`
- `lg` → `min-w-[120px]`
