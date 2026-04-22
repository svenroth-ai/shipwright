/*
 * Iterate 3.7e-b3 (2026-04-22) — shared color picker for the Create
 * wizard + Project Settings dialog.
 *
 * Layout: 8 curated warm-palette swatches (PROJECT_COLOR_PRESETS from
 * lib/projectColor.ts) + an "Auto" option. "Auto" is modeled as
 * `value === null`; when selected the server stores `settings.color`
 * as undefined (deleted), and getProjectColor falls back to the
 * hash-derived hue.
 *
 * Testids:
 *   - wrapper: data-testid="project-color-picker"
 *   - each swatch:  data-testid="project-color-swatch-<value>" (hex lowercase w/out #)
 *                  OR                "project-color-swatch-auto"
 *   - selected swatch has data-selected="true"
 */
import { PROJECT_COLOR_PRESETS } from '../../lib/projectColor';

interface ProjectColorPickerProps {
  /** Current hex value, or null when "Auto" (hash-derived) is active. */
  value: string | null;
  onChange: (value: string | null) => void;
  /** Optional override for the test-id namespace — Create vs Settings. */
  testidPrefix?: string;
}

function swatchTestId(value: string | null, prefix: string): string {
  if (value === null) return `${prefix}-auto`;
  return `${prefix}-${value.replace(/^#/, '').toLowerCase()}`;
}

export function ProjectColorPicker({
  value,
  onChange,
  testidPrefix = 'project-color-swatch',
}: ProjectColorPickerProps) {
  return (
    <div data-testid="project-color-picker">
      <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5 tracking-tight">
        Color
      </label>
      <div className="flex flex-wrap items-center gap-2">
        {/* Auto (hash-derived) — neutral swatch w/ "A" glyph. */}
        <button
          type="button"
          onClick={() => onChange(null)}
          data-testid={swatchTestId(null, testidPrefix)}
          data-selected={value === null ? 'true' : 'false'}
          aria-pressed={value === null}
          aria-label="Auto — derive color from project id"
          title="Auto (hash-derived)"
          className="flex items-center justify-center text-[11px] font-semibold transition-all"
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '9999px',
            background: 'var(--color-muted-bg)',
            color: 'var(--color-muted)',
            border:
              value === null
                ? '2px solid var(--color-primary)'
                : '2px solid transparent',
            boxShadow: value === null ? '0 0 0 2px var(--color-surface) inset' : 'none',
          }}
        >
          A
        </button>
        {PROJECT_COLOR_PRESETS.map((preset) => {
          const isSelected = value?.toLowerCase() === preset.value.toLowerCase();
          return (
            <button
              key={preset.value}
              type="button"
              onClick={() => onChange(preset.value)}
              data-testid={swatchTestId(preset.value, testidPrefix)}
              data-selected={isSelected ? 'true' : 'false'}
              aria-pressed={isSelected}
              aria-label={`${preset.label} (${preset.value})`}
              title={`${preset.label} (${preset.value})`}
              className="transition-all"
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '9999px',
                background: preset.value,
                border: isSelected
                  ? '2px solid var(--color-primary)'
                  : '2px solid transparent',
                boxShadow: isSelected
                  ? '0 0 0 2px var(--color-surface) inset'
                  : 'none',
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
