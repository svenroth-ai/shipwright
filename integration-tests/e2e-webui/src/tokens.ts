// Brand tokens declared in the package's visual-guidelines.md as `--color-bg: #f6f7f9` / `--font-size-base: 16px`
// lines (the only form the intake check recognises), and the comparison with what the served board declares.
export type Tokens = Record<string, string>;

const DECL = /(--(?:color|font-size)-[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8}\b|\d+(?:\.\d+)?px)/g;

export function parseTokens(markdown: string): Tokens {
  const out: Tokens = {};
  for (const m of markdown.matchAll(DECL)) out[m[1]] = m[2];
  return out;
}

/** Hex in lower case with 3-digit shorthand expanded; rgb(r, g, b) becomes hex; anything else is lower-cased and trimmed. */
export function normalise(value: string): string {
  const v = value.trim().toLowerCase();
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(v);
  if (short) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`;
  const rgb = /^rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)\s*\)$/.exec(v);
  if (rgb) return `#${[rgb[1], rgb[2], rgb[3]].map((n) => Number(n).toString(16).padStart(2, "0")).join("")}`;
  return v;
}

export interface TokenCheck {
  declared: number;
  matching: number;
  mismatches: string[];
}

/** Compares each declared token with the value the board's :root carries (empty string = the board does not declare it). */
export function compareTokens(declared: Tokens, served: Tokens): TokenCheck {
  const names = Object.keys(declared);
  const mismatches = names
    .filter((n) => normalise(served[n] ?? "") !== normalise(declared[n]))
    .map((n) => `${n}: package ${declared[n]}, board ${served[n] ? served[n] : "not declared"}`);
  return { declared: names.length, matching: names.length - mismatches.length, mismatches };
}

// Font families (`- --font-family: Inter` / `- --font-mono: Geist Mono`): the intake check ignores them, so the
// harness reads them itself. A served value passes when it names the declared family (fallbacks and quotes allowed).
const FONT_DECL = /^[-*\s]*(--font-(?:family|mono))\s*:\s*([^\r\n]+?)\s*$/gm;

export function parseFontTokens(markdown: string): Tokens {
  const out: Tokens = {};
  for (const m of markdown.matchAll(FONT_DECL)) out[m[1]] = m[2].replace(/[`'"]/g, "").trim();
  return out;
}

/** The first family a font stack names, lower case, without quotes. */
const firstFamily = (stack: string): string => (stack.split(",")[0] ?? "").replace(/['"`]/g, "").trim().toLowerCase();

export function compareFonts(declared: Tokens, served: Tokens): TokenCheck {
  const names = Object.keys(declared);
  const mismatches = names
    .filter((n) => firstFamily(served[n] ?? "") !== firstFamily(declared[n]))
    .map((n) => `${n}: package ${declared[n]}, board ${served[n] ? served[n] : "not declared"}`);
  return { declared: names.length, matching: names.length - mismatches.length, mismatches };
}
