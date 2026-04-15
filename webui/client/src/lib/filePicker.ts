/**
 * Iterate 14.7.1 — clipboard-based "directory picker".
 *
 * Background: the File System Access API (`window.showDirectoryPicker`) is
 * fundamentally unsuited for our use case. It returns a sandboxed
 * `FileSystemDirectoryHandle` whose `name` is ONLY the last path segment
 * (e.g. `my-app`), not the full OS-level absolute path. Browsers hide the
 * absolute path on purpose — no API exposes it, and there is no workaround.
 *
 * Iterate 14.6 shipped a Browse button that called `showDirectoryPicker()`
 * and populated the path input with `handle.name`, producing a broken
 * half-path that users then had to edit manually anyway. The fix is to
 * drop the dialog entirely and offer a "Paste" helper that reads clipboard
 * text and inserts it into the field. That is genuinely useful — users
 * typically copy a path from Explorer/Finder, click Paste, and submit.
 *
 * The field remains freely editable for users who prefer to type.
 */

export async function pasteFromClipboard(): Promise<string | null> {
  try {
    if (typeof navigator === 'undefined' || !navigator.clipboard?.readText) return null;
    const value = await navigator.clipboard.readText();
    if (!value) return null;
    return value;
  } catch {
    return null;
  }
}

/** Heuristic: does this string look like a filesystem path? Used by callers
 *  that want to ignore clipboard contents that are obviously not paths
 *  (random text, URLs, etc.). We accept any string containing `/` or `\`,
 *  or a drive-letter prefix like `C:`. */
export function looksLikePath(value: string): boolean {
  if (!value) return false;
  const trimmed = value.trim();
  if (trimmed.length === 0) return false;
  if (/^[a-zA-Z]:[\\/]/.test(trimmed)) return true;
  return trimmed.includes('/') || trimmed.includes('\\');
}
