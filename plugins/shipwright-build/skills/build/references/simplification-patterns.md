# Code Simplification Patterns

Reference for the readability axis of code review. Simplicity is about
**comprehension speed**, not line count.

---

## Structural Complexity

### Deep Nesting (> 3 levels)
Extract guard clauses or helper functions.
```typescript
// BAD
function process(data) {
  if (data) {
    if (data.items) {
      for (const item of data.items) {
        if (item.active) {
          // actual logic buried 4 levels deep
        }
      }
    }
  }
}

// GOOD: guard clauses
function process(data) {
  if (!data?.items) return;
  for (const item of data.items) {
    if (!item.active) continue;
    // actual logic at 1 level
  }
}
```

### Long Functions (> 50 lines)
Split into focused, named functions. Each function should do one thing.

### Nested Ternaries
Replace with `if/else`, `switch`, or lookup objects.
```typescript
// BAD
const label = status === 'active' ? 'Active' : status === 'pending' ? 'Pending' : status === 'error' ? 'Error' : 'Unknown';

// GOOD
const STATUS_LABELS = { active: 'Active', pending: 'Pending', error: 'Error' };
const label = STATUS_LABELS[status] ?? 'Unknown';
```

### Boolean Parameter Flags
Use options objects or separate functions instead of `doThing(true, false, true)`.

---

## Naming

- **Generic names** (`data`, `result`, `temp`, `val`) → use descriptive names reflecting content
- **Abbreviations** (`usr`, `cfg`, `btn`) → expand unless universally understood in the codebase
- **Misleading names** → rename to reflect actual behavior (e.g., `getData` that also writes = wrong name)

---

## Redundancy

- **Duplicated logic** (5+ lines repeated) → extract to shared function
- **Dead code** → remove unreachable branches and unused variables
- **Unnecessary wrappers** → inline single-use abstractions that add no clarity
- **Over-engineering** → replace factory-of-factories with direct approach
- **Redundant type assertions** → remove where TypeScript infers correctly

---

## When NOT to Simplify

- Code you don't fully understand (read first, simplify second)
- Code outside the current section's scope (don't scope-creep)
- Working code where the "simplification" is subjective style preference
- Performance-critical code where the "complex" version is measurably faster
