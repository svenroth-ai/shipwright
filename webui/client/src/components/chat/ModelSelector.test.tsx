import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useState } from 'react';
import { ModelSelector, KNOWN_MODELS, matchKnownModel, aliasFromConcrete } from './ModelSelector';
import type { ModelOption } from '../../hooks/useChatSettings';

/**
 * Iterate 14.7.1 — ModelSelector overhaul. These tests assert the dropdown
 * now surfaces all five known CLI model ids, auto-syncs to system/init on
 * first event, respects manual override, and survives unknown ids via the
 * "Other: {raw}" fallback.
 */

function openPopover() {
  fireEvent.click(screen.getByTestId('model-selector-trigger'));
}

describe('ModelSelector', () => {
  it('renders all five known CLI models in the dropdown', () => {
    const onChange = vi.fn();
    render(<ModelSelector model="sonnet" onChange={onChange} />);
    openPopover();
    // formatModelLabel turns claude-opus-4-6 → "Opus 4.6" etc. The trigger
    // also renders one of these labels (the active one), so some names
    // legitimately appear twice (trigger + option). Use getAllByText for
    // the active family and getByText for the rest.
    expect(screen.getAllByText('Sonnet 4.6').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Opus 4.6')).toBeInTheDocument();
    expect(screen.getByText('Opus 4.5')).toBeInTheDocument();
    expect(screen.getByText('Sonnet 4.5')).toBeInTheDocument();
    expect(screen.getByText('Haiku 4.5')).toBeInTheDocument();
    // Context labels shown
    expect(screen.getAllByText('1M ctx').length).toBeGreaterThan(0);
    expect(screen.getAllByText('200K ctx').length).toBeGreaterThan(0);
  });

  it('syncs the displayed label to systemInitModel on first event', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ModelSelector model="sonnet" onChange={onChange} taskKey="p1::t1" />,
    );
    // Initial: stored alias `sonnet` → first matching known model label.
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Sonnet 4.6');

    // CLI reports opus-4-5 — the button should flip.
    rerender(
      <ModelSelector
        model="sonnet"
        onChange={onChange}
        systemInitModel="claude-opus-4-5-20251101"
        taskKey="p1::t1"
      />,
    );
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Opus 4.5');
  });

  it('respects user manual override once clicked, ignoring further systemInit updates', () => {
    const onChange = vi.fn();
    function Wrapper() {
      const [sysInit, setSysInit] = useState<string | undefined>(undefined);
      const [alias, setAlias] = useState<ModelOption>('sonnet');
      return (
        <div>
          <ModelSelector
            model={alias}
            onChange={(m) => {
              setAlias(m);
              onChange(m);
            }}
            systemInitModel={sysInit}
            taskKey="p1::t1"
          />
          <button data-testid="emit-init" onClick={() => setSysInit('claude-haiku-4-5')}>
            emit
          </button>
        </div>
      );
    }
    render(<Wrapper />);

    // User manually picks Opus 4.6 before any systemInit event arrives.
    openPopover();
    fireEvent.click(screen.getByText('Opus 4.6'));
    expect(onChange).toHaveBeenCalledWith('opus');
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Opus 4.6');

    // Now a system/init event with Haiku arrives — must be ignored.
    fireEvent.click(screen.getByTestId('emit-init'));
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Opus 4.6');
  });

  it('renders unknown model as an "Other: {raw}" option and selects it automatically', () => {
    const onChange = vi.fn();
    render(
      <ModelSelector
        model="sonnet"
        onChange={onChange}
        systemInitModel="claude-future-9-9"
        taskKey="p1::t1"
      />,
    );
    // Display shows the "Other: …" label for the unknown id.
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Other: claude-future-9-9');
    // After opening the popover the same label appears as an option (so the
    // text is now present twice — once on the trigger, once in the list).
    openPopover();
    expect(screen.getAllByText('Other: claude-future-9-9').length).toBeGreaterThanOrEqual(2);
  });

  it('resets the override flag when taskKey changes so next task auto-syncs again', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ModelSelector
        model="sonnet"
        onChange={onChange}
        systemInitModel="claude-opus-4-5"
        taskKey="p1::t1"
      />,
    );
    // User overrides to Haiku 4.5 on task 1.
    openPopover();
    fireEvent.click(screen.getByText('Haiku 4.5'));
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Haiku 4.5');

    // Switch to task 2 with a new systemInit model. The override must clear
    // and the new task should show the fresh CLI-reported label.
    rerender(
      <ModelSelector
        model="haiku"
        onChange={onChange}
        systemInitModel="claude-sonnet-4-6"
        taskKey="p2::t2"
      />,
    );
    expect(screen.getByTestId('model-selector-trigger').textContent).toBe('Sonnet 4.6');
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

  it('infers family alias from a concrete id', () => {
    expect(aliasFromConcrete('claude-opus-4-6')).toBe('opus');
    expect(aliasFromConcrete('claude-sonnet-4-5-x')).toBe('sonnet');
    expect(aliasFromConcrete('claude-haiku-4-5')).toBe('haiku');
    expect(aliasFromConcrete('something-weird')).toBe('sonnet'); // safest default
  });

  it('exports exactly five known concrete models', () => {
    expect(KNOWN_MODELS).toHaveLength(5);
    expect(KNOWN_MODELS.map((m) => m.id)).toEqual([
      'claude-opus-4-6',
      'claude-opus-4-5',
      'claude-sonnet-4-6',
      'claude-sonnet-4-5',
      'claude-haiku-4-5',
    ]);
  });
});
