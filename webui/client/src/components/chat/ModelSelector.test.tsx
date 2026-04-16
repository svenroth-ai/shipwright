import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ModelSelector, KNOWN_MODELS, matchKnownModel, aliasFromConcrete } from './ModelSelector';

/**
 * Iterate 14.8.3 — ModelSelector redesign. Tests assert the new
 * purely-props-driven contract: no localStorage, no userOverride/
 * displayedId state, no taskKey reset. The selector reads
 * systemInitModel to compute the label, and fires onSwitchModel
 * when the user picks an option.
 */

function openPopover() {
  fireEvent.click(screen.getByTestId('model-selector-trigger'));
}

describe('ModelSelector', () => {
  it('renders label from systemInitModel', () => {
    const onSwitchModel = vi.fn();
    render(
      <ModelSelector
        systemInitModel="claude-opus-4-5-20251101"
        onSwitchModel={onSwitchModel}
      />,
    );
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Opus 4.5');
  });

  it('renders default label (via formatModelLabel) when no systemInitModel', () => {
    const onSwitchModel = vi.fn();
    render(<ModelSelector onSwitchModel={onSwitchModel} />);
    // With no systemInitModel, activeId falls back to KNOWN_MODELS[0].id
    // which is claude-opus-7-0 (iterate 14.9 newest flagship) → "Opus 7.0"
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Opus 7.0');
  });

  it('click option calls onSwitchModel(id)', () => {
    const onSwitchModel = vi.fn();
    render(
      <ModelSelector
        systemInitModel="claude-opus-4-5"
        onSwitchModel={onSwitchModel}
      />,
    );
    openPopover();
    fireEvent.click(screen.getByText('Sonnet 4.6'));
    expect(onSwitchModel).toHaveBeenCalledWith('claude-sonnet-4-6');
  });

  it('unknown model shows "Other: {id}" label', () => {
    const onSwitchModel = vi.fn();
    render(
      <ModelSelector
        systemInitModel="claude-future-9-9"
        onSwitchModel={onSwitchModel}
      />,
    );
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Other: claude-future-9-9');
    // After opening popover, the same label appears as an option
    openPopover();
    expect(screen.getAllByText('Other: claude-future-9-9').length).toBeGreaterThanOrEqual(2);
  });

  it('renders all known CLI models in the dropdown (iterate 14.9: Opus 7 added)', () => {
    const onSwitchModel = vi.fn();
    render(<ModelSelector onSwitchModel={onSwitchModel} />);
    openPopover();
    // With no systemInitModel, KNOWN_MODELS[0] (Opus 7.0) is the default
    // active entry and also an option — so both the trigger label and the
    // option share the "Opus 7.0" text. Use getAllByText for those.
    expect(screen.getAllByText('Opus 7.0').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Opus 4.6').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Opus 4.5').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Sonnet 4.6').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Sonnet 4.5').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Haiku 4.5').length).toBeGreaterThan(0);
    // Context labels shown
    expect(screen.getAllByText('1M ctx').length).toBeGreaterThan(0);
    expect(screen.getAllByText('200K ctx').length).toBeGreaterThan(0);
  });

  it('shows Running: tooltip when systemInitModel is set', () => {
    const onSwitchModel = vi.fn();
    render(
      <ModelSelector
        systemInitModel="claude-sonnet-4-6"
        onSwitchModel={onSwitchModel}
      />,
    );
    expect(screen.getByTestId('model-selector-trigger').title).toBe('Running: claude-sonnet-4-6');
  });

  it('shows generic tooltip when no systemInitModel', () => {
    const onSwitchModel = vi.fn();
    render(<ModelSelector onSwitchModel={onSwitchModel} />);
    expect(screen.getByTestId('model-selector-trigger').title).toBe('Claude CLI model');
  });
});

describe('matchKnownModel / aliasFromConcrete', () => {
  it('matches known ids directly and with CLI date suffix', () => {
    expect(matchKnownModel('claude-opus-4-6')?.id).toBe('claude-opus-4-6');
    expect(matchKnownModel('claude-opus-4-5-20251101')?.id).toBe('claude-opus-4-5');
    expect(matchKnownModel('gpt-5')).toBeNull();
    expect(matchKnownModel(null)).toBeNull();
    expect(matchKnownModel(undefined)).toBeNull();
  });

  // Iterate 14.9 — Opus 7 support.
  it('matches claude-opus-7-0 and its date-suffixed form', () => {
    expect(matchKnownModel('claude-opus-7-0')?.id).toBe('claude-opus-7-0');
    expect(matchKnownModel('claude-opus-7-0-20260401')?.id).toBe('claude-opus-7-0');
  });

  it('infers opus alias for claude-opus-7-0', () => {
    expect(aliasFromConcrete('claude-opus-7-0')).toBe('opus');
  });

  it('infers family alias from a concrete id', () => {
    expect(aliasFromConcrete('claude-opus-4-6')).toBe('opus');
    expect(aliasFromConcrete('claude-sonnet-4-5-x')).toBe('sonnet');
    expect(aliasFromConcrete('claude-haiku-4-5')).toBe('haiku');
    expect(aliasFromConcrete('something-weird')).toBe('sonnet'); // safest default
  });

  it('exports the expected concrete models with Opus 7 at the top (iterate 14.9)', () => {
    expect(KNOWN_MODELS).toHaveLength(6);
    expect(KNOWN_MODELS.map((m) => m.id)).toEqual([
      'claude-opus-7-0',
      'claude-opus-4-6',
      'claude-opus-4-5',
      'claude-sonnet-4-6',
      'claude-sonnet-4-5',
      'claude-haiku-4-5',
    ]);
  });
});
