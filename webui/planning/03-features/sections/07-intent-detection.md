# Section 07: Intent Detection Hint (Task Detail Chat)

## Goal

Add a non-blocking intent detection hint inside the Task Detail chat input area. When a user types a message that is classified as a code change (bug, feature, or change) with confidence >= 0.7, a subtle hint appears below the input suggesting the detected intent. Implements guard rules to skip classification for slash commands, questions, greetings, and short messages. This is a MAY-priority enhancement.

## FRs Covered

- **FR-03.20** — The system MAY display a non-blocking Intent Detection hint inside the Task Detail chat when a typed message is classified as a code change with confidence >= 0.7.
- **FR-03.21** — The system SHALL skip intent detection for slash commands, questions containing "?", greetings, and messages shorter than 10 characters.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/utils/intentGuards.ts` | Pure guard functions for skip conditions |
| `client/src/hooks/useIntentDetection.ts` | Debounced classification hook with guards |
| `client/src/components/chat/IntentHint.tsx` | Hint display with intent label, confidence, dismiss |
| `client/src/utils/intentGuards.test.ts` | Tests for guard functions |
| `client/src/hooks/useIntentDetection.test.ts` | Tests for detection hook |
| `client/src/components/chat/IntentHint.test.tsx` | Tests for hint component |

## Files to Modify

| File | Change |
|------|--------|
| `client/src/components/chat/ChatInput.tsx` (from Split 02) | Integrate IntentHint below input, pass current message text to useIntentDetection |

## Implementation Steps

1. **Create guard functions** in `client/src/utils/intentGuards.ts`:
   - `shouldSkipClassification(message: string): boolean` — returns `true` if any guard matches:
     - `isSlashCommand(message)`: starts with `/`
     - `isQuestion(message)`: contains `?`
     - `isGreeting(message)`: matches common greetings list (`hi`, `hello`, `hey`, `good morning`, `good afternoon`, `good evening`, `howdy`, `hiya`, case-insensitive, trimmed)
     - `isTooShort(message)`: `message.trim().length < 10`
   - All functions exported individually for testing
   - `GREETING_PATTERNS` constant: `['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'howdy', 'hiya']`

2. **Create `useIntentDetection` hook** in `client/src/hooks/useIntentDetection.ts`:
   - Accepts `message: string`, `projectId: string`
   - Debounces the message at 500ms (QR-03.03) using a `useDebouncedValue` utility
   - When debounced message changes:
     - If `shouldSkipClassification(message)` returns true, set result to null
     - Otherwise, call classify endpoint: POST `/api/projects/${projectId}/classify` with `{ text: debouncedMessage, mode: 'intent-only' }`
   - Uses `useQuery` with key `['intent-detection', projectId, debouncedMessage]` and `enabled: !shouldSkip && debouncedMessage.length > 0`
   - Returns `{ intent: string | null, confidence: number | null, isClassifying: boolean }`
   - Only exposes result when confidence >= 0.7 (FR-03.20 threshold)
   - `staleTime: 10_000` to avoid re-classifying the same text

3. **Create `IntentHint` component** in `client/src/components/chat/IntentHint.tsx`:
   - Accepts `intent: string | null`, `confidence: number | null`, `onDismiss: () => void`
   - If `intent` is null or `confidence` is null or < 0.7, renders nothing
   - Otherwise renders a subtle hint bar below the chat input:
     ```
     ╰─ Hint: looks like a "{intent}" ({confidence}) — [dismiss]
     ```
   - Styling: `text-xs text-muted-foreground`, slightly indented, background `bg-muted/50`, rounded, `py-1 px-3`
   - "dismiss" is a button that calls `onDismiss` (hides hint for this message)
   - Non-blocking: does not prevent typing or sending the message
   - Animation: fade-in on appearance (`animate-in fade-in duration-200`)
   - ARIA: `role="status"`, `aria-live="polite"` for screen reader announcement

4. **Modify `ChatInput` component** (from Split 02 Section 08):
   - Add state: `isDismissed: boolean` (reset to false when message text changes significantly)
   - Call `useIntentDetection(messageText, projectId)`
   - Render `<IntentHint intent={result.intent} confidence={result.confidence} onDismiss={() => setIsDismissed(true)} />` below the input textarea
   - Only show IntentHint when `!isDismissed`
   - Reset `isDismissed` to false when message text changes by more than 10 characters from the text at dismissal time

## Test Strategy

### Unit Tests

**`client/src/utils/intentGuards.test.ts`**:
- `isSlashCommand('/build')` returns true
- `isSlashCommand('build something')` returns false
- `isQuestion('what is this?')` returns true
- `isQuestion('fix the bug')` returns false
- `isGreeting('hi')` returns true
- `isGreeting('Hello')` returns true (case insensitive)
- `isGreeting('fix the auth')` returns false
- `isTooShort('hey')` returns true (< 10 chars)
- `isTooShort('fix the authentication redirect bug')` returns false
- `shouldSkipClassification('/test')` returns true
- `shouldSkipClassification('what?')` returns true
- `shouldSkipClassification('hello')` returns true
- `shouldSkipClassification('short')` returns true
- `shouldSkipClassification('fix the authentication redirect bug')` returns false

### Hook Tests

**`client/src/hooks/useIntentDetection.test.ts`** (renderHook + MSW):
- Returns null intent when message is a slash command
- Returns null intent when message is a question
- Returns null intent when message is a greeting
- Returns null intent when message is too short
- Calls classify API for valid messages after debounce
- Returns intent and confidence when confidence >= 0.7
- Returns null when confidence < 0.7
- Debounces API calls at 500ms

### Component Tests

**`client/src/components/chat/IntentHint.test.tsx`**:
- Renders nothing when intent is null
- Renders nothing when confidence < 0.7
- Renders hint with intent label and confidence when >= 0.7
- Clicking dismiss calls onDismiss
- Has role="status" and aria-live="polite"
- Hint has fade-in animation class

## Dependencies

- **Split 02 Section 08** — ChatInput component (provides the input area to attach the hint)
- **Split 01 Section 10** — POST /api/projects/:id/classify endpoint (intent-only mode)

## Acceptance Criteria

**FR-03.20: Intent Detection Hint**
- [ ] Subtle hint appears in Task Detail chat when confidence >= 0.7
- [ ] Hint shows detected intent and confidence score
- [ ] Hint is dismissible and non-blocking

**FR-03.21: Intent Detection Guards**
- [ ] Messages starting with "/" are not classified
- [ ] Messages containing "?" are not classified
- [ ] Messages shorter than 10 characters are not classified
- [ ] Common greetings are not classified
