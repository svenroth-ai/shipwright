# Step 3 — Design Interview (3-5 questions)

**Goal:** Refine the proposal with user preferences. Quick, targeted.

```
AskUserQuestion:
  question: "Quick design questions before I generate mockups:"
```

**Questions to ask:**

1. **Design System Flavor**: "Which design system should I use as the visual foundation?"
   - **Untitled UI** — Clean, professional SaaS style (default)
   - **Material Design 3** — Google's design system, great for consumer apps
   - **Custom** — Upload your own guidelines to `.shipwright/designs/uploads/`
   See [design-flavors.md](design-flavors.md) for details.
2. **Brand Character**: "What character should the app have?"
   - **A) Warm & Premium** — Earth tones, beige/cream backgrounds, elegant feel (think: luxury brands, boutique)
   - **B) Clean & Modern** — Whites, subtle grays, one accent color (think: Stripe, Linear)
   - **C) Bold & Energetic** — Vibrant colors, strong contrasts (think: Vercel, Figma)
   - **D) I have specific brand guidelines** → upload to `.shipwright/designs/uploads/`
   If brand tokens were extracted in Step 2.5, present them here as suggestion and let the user confirm or override.
   See [design-system-patterns.md](design-system-patterns.md) → "Character Palettes" for full token sets.
3. **Layout**: "Sidebar navigation or top navigation bar?"
4. **Existing designs**: "Do you have existing mockups or screenshots to include? Drop them in .shipwright/designs/uploads/ if so."
5. **Special UX**: "Any specific UX requirements? (dark mode, mobile-first, accessibility focus, etc.)"

**Palette derivation:** After the user picks a character (or confirms extracted tokens), derive the full palette automatically:

| Character | Background | Card Style | Accent Strategy |
|-----------|-----------|------------|-----------------|
| Warm & Premium | Cream/beige (#f5f0eb) | Shadow, no border, 12px radius | Brown/earth tones from bg |
| Clean & Modern | White (#ffffff) | 1px border + subtle shadow, 8px radius | Single saturated color |
| Bold & Energetic | White or dark | Strong shadow, 8px radius | 2-color system (primary + secondary) |

**Flavor resolution:** User choice > profile default (`design_system.name`) > `untitled-ui`.

**If custom flavor selected:** Prompt user to upload guidelines to `.shipwright/designs/uploads/`. Read them and use as the design foundation for all mockups. Skip generating new guidelines in Step 6.5 — instead, reference the uploaded file.

**Then present the proposed screen list:**

```
Based on your specs, I'll generate these screens:

Screens:
  01. Login (FR-01.01, FR-01.02)
  02. Dashboard (FR-02.01)
  03. Task List (FR-02.02, FR-02.03)
  04. Task Form (FR-02.04)
  05. Settings (FR-03.01)

User Flows:
  A. Auth Flow: Login → Register → Verify → Dashboard
  B. CRUD Flow: List → Detail → Edit → Delete Confirm

Add, remove, or modify?
```
