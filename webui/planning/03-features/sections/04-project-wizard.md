# Section 04: Project Wizard — 4-Step Creation Flow

## Goal

Build a full-screen modal wizard for creating new Shipwright projects. The wizard guides the user through four steps: project name/directory/description, stack profile/autonomy level, environment variables (dynamically populated from selected profile), and a confirmation summary. The wizard validates directory existence, registers the project via POST /api/projects, adds it as a new tab on the Kanban board, and automatically starts the pipeline.

**Design reference:** `screens/05-project-wizard.html`

## FRs Covered

- **FR-03.15** — The system SHALL provide a 4-step Project Wizard modal (Name/Directory/Description, Stack Profile/Autonomy, Environment Variables, Confirmation).
- **FR-03.16** — The system SHALL validate that the selected project directory exists before allowing the wizard to proceed past Step 1.
- **FR-03.17** — The system SHALL register the new project, add it as a new tab on the Kanban board, and automatically start the pipeline after wizard completion.
- **FR-03.25** — The system SHOULD populate the Project Wizard Step 3 dynamically based on the selected stack profile.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/wizard/ProjectWizard.tsx` | Modal shell with step indicator and Back/Next/Start navigation |
| `client/src/components/wizard/StepIndicator.tsx` | 4-step progress indicator (numbered circles + labels) |
| `client/src/components/wizard/steps/ProjectInfoStep.tsx` | Step 1: name, directory (with validation), description |
| `client/src/components/wizard/steps/StackProfileStep.tsx` | Step 2: stack profile radio, autonomy radio |
| `client/src/components/wizard/steps/EnvVarsStep.tsx` | Step 3: dynamic key-value environment variable editor |
| `client/src/components/wizard/steps/ConfirmationStep.tsx` | Step 4: read-only summary of all entered data |
| `client/src/hooks/useCreateProject.ts` | TanStack Query mutation for POST /api/projects |
| `client/src/hooks/useValidateDirectory.ts` | Debounced directory validation via backend |
| `client/src/hooks/useStackProfiles.ts` | Query hook for available stack profiles + env var templates |
| `client/src/types/wizard.ts` | WizardState, WizardStep, StackProfile interfaces |
| `client/src/components/wizard/ProjectWizard.test.tsx` | Tests for wizard flow |
| `client/src/components/wizard/steps/ProjectInfoStep.test.tsx` | Tests for Step 1 validation |
| `client/src/components/wizard/steps/EnvVarsStep.test.tsx` | Tests for dynamic env vars |

## Implementation Steps

1. **Define wizard types** in `client/src/types/wizard.ts`:
   - `WizardStep` union: `1 | 2 | 3 | 4`
   - `StackProfile` interface: `{ id: string; name: string; description: string; envVars: Array<{ key: string; required: boolean; description: string }> }`
   - `WizardState` interface:
     ```typescript
     interface WizardState {
       name: string;
       directory: string;
       description: string;
       profileId: string;
       autonomy: 'guided' | 'autonomous';
       envVars: Record<string, string>;
     }
     ```

2. **Create `useValidateDirectory` hook** in `client/src/hooks/useValidateDirectory.ts`:
   - Accepts `directory: string`
   - Uses `useQuery` with key `['validate-dir', directory]` and `enabled: directory.length > 0`
   - Fetches `GET /api/projects/validate-dir?path=${encodeURIComponent(directory)}`
   - Debounced: sets `staleTime: 0` and relies on query key change; wraps the directory input with a 500ms debounce (use a `useDebouncedValue` utility)
   - Returns `{ isValid: boolean | undefined, isValidating: boolean }`

3. **Create `useStackProfiles` hook** in `client/src/hooks/useStackProfiles.ts`:
   - Uses `useQuery` with key `['stack-profiles']`
   - Fetches `GET /api/settings/profiles` (returns available stack profiles with env var templates)
   - `staleTime: Infinity` (profiles don't change during a session)
   - Returns `{ profiles: StackProfile[], isLoading }`

4. **Create `useCreateProject` hook** in `client/src/hooks/useCreateProject.ts`:
   - Uses `useMutation` to POST to `/api/projects`
   - Body: full `WizardState` payload
   - On success: invalidates `['projects']` query to refresh the sidebar/board tab list, then navigates to the new project's board
   - Returns `{ createProject, isCreating, error }`

5. **Create `StepIndicator` component** in `client/src/components/wizard/StepIndicator.tsx`:
   - Accepts `currentStep: WizardStep`, `steps: Array<{ number: number; label: string }>`
   - Renders 4 circles connected by lines
   - Completed steps: filled circle with checkmark, primary color
   - Current step: filled circle with step number, primary color, slightly larger
   - Future steps: outlined circle with step number, muted color
   - Labels below each circle
   - Responsive: labels hidden on narrow viewports, circles remain

6. **Create `ProjectInfoStep`** (Step 1) in `client/src/components/wizard/steps/ProjectInfoStep.tsx`:
   - Form fields:
     - **Name**: `<input>` with label, required, auto-focused
     - **Directory**: `<input>` with label + "Browse" button (triggers native directory picker if available, otherwise just text input). Below the input, shows validation status via `useValidateDirectory`:
       - Validating: spinner + "Checking..."
       - Valid: green checkmark + "Directory exists"
       - Invalid: red X + "Directory not found"
     - **Description**: `<textarea>` with label, optional
   - "Next" button: disabled until name is non-empty AND directory is validated as existing (FR-03.16)
   - All fields update parent `WizardState` via onChange callbacks

7. **Create `StackProfileStep`** (Step 2) in `client/src/components/wizard/steps/StackProfileStep.tsx`:
   - Uses `useStackProfiles()` to get available profiles
   - **Profile selection**: Radix `RadioGroup` with one option per profile. Each shows name + short description.
   - **Autonomy level**: Radix `RadioGroup` with two options: "Guided" (description: "Claude asks before major changes") and "Autonomous" (description: "Claude proceeds independently")
   - Default: first profile selected, "Guided" autonomy
   - "Back" and "Next" buttons; Next always enabled (valid defaults exist)

8. **Create `EnvVarsStep`** (Step 3) in `client/src/components/wizard/steps/EnvVarsStep.tsx`:
   - Reads selected `profileId` from wizard state
   - Fetches env var template from the selected profile's `envVars` array (FR-03.25)
   - Renders a key-value editor: for each env var template entry:
     - Label: `key` (e.g., `NEXT_PUBLIC_SUPABASE_URL`)
     - Input: text field for value
     - Required indicator: red asterisk if `required: true`
     - Description: small help text below input
   - User can add custom key-value pairs via "Add Variable" button at the bottom
   - Custom vars: two text inputs (key + value) per row, with a remove button
   - "Back" and "Next" buttons; Next disabled if any required env vars are empty

9. **Create `ConfirmationStep`** (Step 4) in `client/src/components/wizard/steps/ConfirmationStep.tsx`:
   - Renders a read-only summary of all wizard state:
     - Name, Directory, Description
     - Stack Profile name, Autonomy level
     - Environment variables count + list (masked values for sensitive-looking keys like `*KEY*`, `*SECRET*`, `*TOKEN*`)
   - "Back" button to return to previous steps
   - "Start" button: triggers `createProject` mutation, shows loading spinner while creating
   - On success: closes wizard modal, project appears as new board tab (FR-03.17)

10. **Create `ProjectWizard` component** in `client/src/components/wizard/ProjectWizard.tsx`:
    - Uses Radix `Dialog` for the modal (C-03.01)
    - Full-screen overlay style: `max-w-2xl mx-auto mt-16`, backdrop blur
    - State: `currentStep: WizardStep` (starts at 1), `wizardState: WizardState`
    - Renders `StepIndicator` at the top
    - Renders the current step component in the body
    - Step components receive `wizardState` + `onUpdate` + `onNext` + `onBack` props
    - `onNext`: increments step (1->2->3->4)
    - `onBack`: decrements step (4->3->2->1)
    - Close button (X) in top-right corner with confirmation if any data entered
    - Keyboard: Escape closes the dialog (Radix default)

## Test Strategy

### Unit Tests

**`client/src/hooks/useValidateDirectory.test.ts`** (renderHook + MSW):
- Returns isValid=true for existing directory
- Returns isValid=false for non-existent directory
- Debounces validation calls (only one request after rapid input)

### Component Tests

**`client/src/components/wizard/ProjectWizard.test.tsx`**:
- Renders Step 1 by default
- Step indicator shows step 1 as current
- Clicking Next advances to Step 2 (when Step 1 is valid)
- Clicking Back returns to previous step
- Cannot advance past Step 1 with empty name
- Cannot advance past Step 1 with invalid directory
- Step 4 Start button triggers createProject mutation
- Modal closes on successful project creation

**`client/src/components/wizard/steps/ProjectInfoStep.test.tsx`**:
- Name field is auto-focused
- Next button disabled when name is empty
- Next button disabled when directory is invalid
- Next button enabled when name filled and directory valid
- Directory validation shows correct status indicators

**`client/src/components/wizard/steps/EnvVarsStep.test.tsx`**:
- Renders env var fields from selected profile template
- Required fields show asterisk indicator
- Next button disabled when required fields are empty
- "Add Variable" button adds a new custom key-value row
- Remove button removes a custom variable row

## Dependencies

- **Split 02 Section 02** — Layout/routing for modal trigger (e.g., sidebar "New Project" button)
- **Split 02 Section 03** — Data hooks pattern (TanStack Query)
- **Split 01 Section 10** — POST /api/projects, GET /api/settings/profiles, directory validation endpoint
- **Design reference** — `screens/05-project-wizard.html`

## Acceptance Criteria

**FR-03.15: Project Wizard Steps**
- [ ] Step 1 collects name, directory path, and description
- [ ] Step 2 offers stack profile selection and autonomy level
- [ ] Step 3 shows environment variable fields appropriate to selected profile
- [ ] Step 4 displays confirmation summary
- [ ] User can navigate back to previous steps

**FR-03.16: Directory Validation**
- [ ] Wizard validates directory path exists
- [ ] Inline error for non-existent directory
- [ ] Next button disabled until directory is valid

**FR-03.17: Project Registration + Pipeline Start**
- [ ] Project is registered after confirmation
- [ ] Project appears as new tab on the Kanban board
- [ ] Pipeline starts automatically

**FR-03.25: Dynamic Env Vars**
- [ ] Step 3 populates env var fields based on selected stack profile from Step 2
