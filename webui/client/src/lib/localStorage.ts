/**
 * Iterate 14.7.0 — typed localStorage get/set helpers.
 *
 * Why not use `useLocalStorage` hook for everything? Some call sites
 * (lazy `useState` initial values, non-React code, tests) need the raw
 * synchronous read without the state-machine overhead. These helpers
 * swallow every error path — parse failures, SSR environments where
 * `window` is undefined, private-mode quota errors — and return the
 * fallback so callers never need a try/catch.
 */
export function getStored<T>(key: string, fallback: T): T {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return fallback;
    }
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function setStored<T>(key: string, value: T): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode / quota exceeded — silently ignore. The next
    // getStored call will fall back to the default, which is fine.
  }
}
