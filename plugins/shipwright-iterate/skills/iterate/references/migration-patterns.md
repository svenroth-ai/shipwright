# Migration & Deprecation Patterns

Reference for the CHANGE path in /shipwright-iterate when refactoring or replacing
existing functionality.

---

## When to Apply

- Replacing a library, API, or internal module with a new implementation
- Consolidating duplicate implementations
- Removing deprecated features
- Major refactoring that changes interfaces used by other modules

---

## Patterns

### Strangler Pattern
Run old and new systems in parallel, incrementally routing traffic to the new system.

1. Build the replacement alongside the old system
2. Route a small percentage of traffic/calls to the new system
3. Monitor for correctness and performance parity
4. Gradually increase routing (10% → 50% → 100%)
5. Remove old system only after 100% routing is stable

**Use when:** Replacing large systems where big-bang cutover is too risky.

### Adapter Pattern
Create an adapter that translates the old interface to the new implementation.
Consumers keep using the familiar API while the backend migrates.

```typescript
// Old interface consumers expect
function getUser(id: string): OldUserFormat { ... }

// Adapter: old interface → new implementation
function getUser(id: string): OldUserFormat {
  const newUser = newUserService.findById(id);
  return toOldFormat(newUser);  // transform to expected shape
}
```

**Use when:** Many consumers depend on the old interface and can't all migrate at once.

### Feature Flag Migration
Use feature flags to switch between old and new implementations per-user or per-environment.

```typescript
if (featureFlags.isEnabled('new-payment-flow', user)) {
  return newPaymentFlow(order);
} else {
  return legacyPaymentFlow(order);
}
```

**Use when:** You need gradual rollout with per-user/per-environment control.

---

## Deprecation Checklist

Before removing old code:

1. **Replacement exists and is proven** — new system handles all critical use cases
2. **All consumers migrated** — verify via grep, usage metrics, or dependency analysis
3. **No remaining references** — search codebase for imports, type references, config entries
4. **Tests updated** — old tests removed or migrated, new tests cover replacement
5. **Documentation updated** — no stale references to removed functionality

---

## Key Principle

> "Code is a liability, not an asset."
> Every line requires maintenance — bug fixes, dependency updates, security patches.
> Removing code that no longer provides value is an achievement, not a loss.
