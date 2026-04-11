import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { SlashCommandPopup } from './SlashCommandPopup';

describe('SlashCommandPopup', () => {
  it('renders nothing when not visible', () => {
    const { container } = render(
      <SlashCommandPopup query="" onSelect={vi.fn()} onClose={vi.fn()} visible={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows filtered commands', () => {
    render(
      <SlashCommandPopup query="build" onSelect={vi.fn()} onClose={vi.fn()} visible />,
    );
    expect(screen.getByText('/shipwright-build')).toBeInTheDocument();
    expect(screen.queryByText('/shipwright-test')).not.toBeInTheDocument();
  });

  it('calls onSelect when command clicked', async () => {
    const onSelect = vi.fn();
    render(
      <SlashCommandPopup query="plan" onSelect={onSelect} onClose={vi.fn()} visible />,
    );
    await userEvent.click(screen.getByText('/shipwright-plan'));
    expect(onSelect).toHaveBeenCalledWith('/shipwright-plan');
  });
});
