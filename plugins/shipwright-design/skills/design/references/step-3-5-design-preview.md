# Step 3.5 — Design Preview

**Goal:** Validate the chosen palette and style on a small sample before generating all screens.

**After** the screen list is confirmed in Step 3, generate exactly 3 preview screens:

1. **Auth/Login screen** — Brand first impression, centered card layout
2. **Main layout screen** — Sidebar + content (or top nav), shows navigation feel
3. **One content-heavy screen** — Detail page with cards, buttons, and text hierarchy

Pick these from the confirmed screen list. Save them to `.shipwright/designs/screens/` as usual.

```
AskUserQuestion:
  question: |
    I've generated 3 preview screens. Open them in your browser:
      - .shipwright/designs/screens/{login-screen}.html
      - .shipwright/designs/screens/{layout-screen}.html
      - .shipwright/designs/screens/{content-screen}.html

    Does the look and feel match what you want?
    Specifically: colors, font, card style, overall warmth?
```

**If adjustments needed:**
- Swap hex values / font / radius in the 3 preview files
- Do NOT regenerate from scratch — just update the CSS variables
- Re-ask for confirmation

**Only after user confirms** → proceed to Step 3.7 (Chrome Definition) and then Step 4.
