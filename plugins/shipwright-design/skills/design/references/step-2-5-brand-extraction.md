# Step 2.5 — Brand Extraction

**Goal:** Auto-extract design tokens from the user's existing website before asking design questions.

**Trigger:** If the user has an existing website (mentioned in project interview, requirements, or `shipwright_project_config.json`).

**Skip if:** No existing website is known. Proceed directly to Step 3.

```
1. WebFetch the URL
2. Extract from HTML/CSS:
   - Fonts: <link> tags (Google Fonts), CSS font-family declarations
   - Colors: CSS custom properties, most frequent bg/text/accent colors
   - Background style: white vs. cream/beige vs. dark
   - Card style: border-based vs. shadow-based
   - Border radius patterns
3. Present findings:
   "I found these design tokens from your website:
    - Font: {font} ({weights})
    - Background: {hex} ({description})
    - Text: {hex}
    - Accent: {hex} ({description})
    - Cards: {style}, {radius} radius
    Shall I use these as the foundation?"
4. User confirms or adjusts
```

Confirmed tokens carry forward into Step 3 as defaults — the user can still override them.
