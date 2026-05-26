# Step 2 — Detect Screen Types

**Goal:** Map FRs to screen types automatically.

See [design-system-patterns.md](design-system-patterns.md) for patterns.

Scan each FR for keywords and map to screen types:

| FR Keywords | Screen Type | Default Layout |
|-------------|-----------|---------------|
| login, authenticate, sign in, register | Auth | Centered card with form |
| dashboard, overview, home, summary | Dashboard | Sidebar + header + content grid |
| list, browse, search, filter, table | List/Table | Filter bar + data table + pagination |
| create, add, edit, form, input, new | Form | Form sections + validation + actions |
| settings, profile, preferences, account | Settings | Tabs + form sections |
| detail, view, show, inspect | Detail | Content sections + actions bar |
| onboarding, wizard, setup, welcome | Onboarding | Step-by-step centered flow |
| notification, alert, inbox, messages | Notifications | List with badges + detail panel |

Build a proposed screen list from this analysis.
