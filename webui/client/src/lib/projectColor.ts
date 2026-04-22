// Iterate 14.7.2 — deterministic project → color mapping.
//
// When "All Projects" is active on the Kanban board, every card gets
// a colored left-edge strip so users can visually distinguish which
// project each card belongs to. Colors are derived by hashing the
// stable projectId string to a hue on the HSL wheel. Same projectId
// always produces the same color, across sessions and reloads.
//
// We intentionally use a small number of hues (HUE_STEPS) so the set
// of possible colors stays visually distinct rather than drifting into
// near-duplicates. Collisions are acceptable — the filter chip +
// sidebar legend are the authoritative mapping.

function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

const HUE_STEPS = 12; // 12 distinct hues around the wheel
const SATURATION = 65; // %
const LIGHTNESS = 55; // %

export interface ProjectColor {
  hue: number;
  hsl: string;
  hslStripe: string;
}

/**
 * Iterate 3.7e-b3 (2026-04-22) — curated warm-palette swatches for the
 * project-color picker in the Create / Settings dialogs. 8 hues tuned
 * to sit well on the warm-beige `--color-bg` surface; also contrast OK
 * against `--color-muted-bg` chip backgrounds. The literal hex values
 * are the user-visible canonical form (stored in `settings.color`).
 * "Auto" is represented by the absence of a custom color (undefined).
 */
export const PROJECT_COLOR_PRESETS: ReadonlyArray<{ label: string; value: string }> = [
  { label: "Beige", value: "#B8A590" },
  { label: "Rose", value: "#D99285" },
  { label: "Amber", value: "#E5B85F" },
  { label: "Sage", value: "#8FA68A" },
  { label: "Teal", value: "#6FA3A8" },
  { label: "Slate", value: "#7A8598" },
  { label: "Plum", value: "#9C7A95" },
  { label: "Clay", value: "#C08862" },
];

/**
 * Returns a deterministic color for a project. If `customColor` is
 * provided (from project.settings.color), it is used directly instead
 * of the hash-derived hue. This lets users override the strip color
 * via Settings > Project > Color picker.
 */
export function getProjectColor(projectId: string, customColor?: string): ProjectColor {
  if (customColor) {
    return { hue: 0, hsl: customColor, hslStripe: customColor };
  }
  const hue = (simpleHash(projectId) % HUE_STEPS) * (360 / HUE_STEPS);
  const hsl = `hsl(${hue} ${SATURATION}% ${LIGHTNESS}%)`;
  return {
    hue,
    hsl,
    // Kept as a separate field so we can later tune the strip
    // saturation/lightness independently of the dot legend.
    hslStripe: hsl,
  };
}
