# User Flow Patterns

## Standard Flows

### Authentication Flow
```
Login → [New user?] → Register → Verify Email → Dashboard
                   ↘ Forgot Password → Reset → Login
```

**Screens:**
1. Login (email/password + social OAuth buttons)
2. Register (name, email, password, confirm)
3. Verify Email (confirmation message + resend link)
4. Forgot Password (email input)
5. Reset Password (new password + confirm)

### CRUD Flow (Generic)
```
List → [View] → Detail → [Edit] → Form → [Save] → Detail
    → [Create] → Form → [Save] → List
    → [Delete] → Confirm Dialog → List
```

**Screens:**
1. List (table or cards with filters, search, pagination)
2. Detail (read-only view with edit/delete actions)
3. Create/Edit Form (same form, different title and prefilled data)
4. Delete Confirmation (modal dialog)

### Settings Flow
```
Settings → [Tab: Profile] → Edit Profile → Save
        → [Tab: Security] → Change Password / 2FA
        → [Tab: Notifications] → Toggle Preferences
        → [Tab: Billing] → Plan Selection → Payment
```

### Onboarding Flow
```
Welcome → Step 1 (Profile) → Step 2 (Preferences) → Step 3 (Team) → Dashboard
```

**Screens:** Centered stepper with progress indicator.

### Dashboard → Action Flow
```
Dashboard → [Click metric] → Filtered List → Detail → Action → Confirmation → Dashboard
```

## Flow Mockup Format

Multi-screen flows are generated as single HTML files with:
- Tab navigation or step indicator at top
- Each "screen" as a section
- Visual arrows or step numbers showing progression
- All screens visible (scrollable) for easy review

## Flow Detection from FRs

| FR Pattern | Likely Flow |
|-----------|------------|
| login + register + password | Auth Flow |
| create + list + edit + delete | CRUD Flow |
| settings + profile + preferences | Settings Flow |
| onboarding + welcome + setup | Onboarding Flow |
| dashboard + detail + action | Dashboard Action Flow |
