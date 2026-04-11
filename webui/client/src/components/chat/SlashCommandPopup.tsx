import { useMemo } from 'react';
import { CHAT_COMMANDS } from '../../lib/chatCommands';

interface SlashCommandPopupProps {
  query: string;
  onSelect: (command: string) => void;
  onClose: () => void;
  visible: boolean;
}

export function SlashCommandPopup({ query, onSelect, onClose, visible }: SlashCommandPopupProps) {
  const filtered = useMemo(
    () => CHAT_COMMANDS.filter((c) => c.command.toLowerCase().includes(query.toLowerCase())),
    [query],
  );

  if (!visible || filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 mb-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto w-72 z-50">
      {filtered.map((cmd) => (
        <button
          key={cmd.command}
          className="flex flex-col w-full px-3 py-2 text-left hover:bg-gray-50"
          onClick={() => { onSelect(cmd.command); onClose(); }}
        >
          <span className="text-xs font-mono font-medium text-[var(--color-primary)]">{cmd.command}</span>
          <span className="text-[10px] text-gray-400">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}
