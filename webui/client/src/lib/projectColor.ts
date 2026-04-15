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

export function getProjectColor(projectId: string): ProjectColor {
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
