import { useState, useRef } from 'react';
import { Send } from 'lucide-react';
import { ChatToolbar } from './ChatToolbar';
import { SlashCommandPopup } from './SlashCommandPopup';
import { useChatSettings } from '../../hooks/useChatSettings';
import type { AutonomyOption } from '../../types/settings';

interface ChatInputProps {
  onSend: (message: string, settings: { model: string; mode: string; effort: string; autonomy: string }) => void;
  isStreaming: boolean;
  autonomy: AutonomyOption;
}

export function ChatInput({ onSend, isStreaming, autonomy }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [showSlashPopup, setShowSlashPopup] = useState(false);
  const [slashQuery, setSlashQuery] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const settings = useChatSettings();

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed, { model: settings.model, mode: settings.mode, effort: settings.effort, autonomy });
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === 'Escape') {
      setShowSlashPopup(false);
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value;
    setInput(value);

    // Auto-grow
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
    }

    // Slash command detection
    const lastSlash = value.lastIndexOf('/');
    if (lastSlash >= 0 && (lastSlash === 0 || value[lastSlash - 1] === ' ' || value[lastSlash - 1] === '\n')) {
      const query = value.slice(lastSlash + 1);
      if (!query.includes(' ')) {
        setSlashQuery(query);
        setShowSlashPopup(true);
        return;
      }
    }
    setShowSlashPopup(false);
  }

  function handleSlashSelect(command: string) {
    const lastSlash = input.lastIndexOf('/');
    setInput(input.slice(0, lastSlash) + command + ' ');
    setShowSlashPopup(false);
    textareaRef.current?.focus();
  }

  return (
    <div className="border-t border-gray-200 bg-white">
      <ChatToolbar
        model={settings.model}
        setModel={settings.setModel}
        mode={settings.mode}
        setMode={settings.setMode}
        effort={settings.effort}
        setEffort={settings.setEffort}
        autonomy={autonomy}
      />
      <div className="relative px-3 pb-3">
        <SlashCommandPopup
          query={slashQuery}
          onSelect={handleSlashSelect}
          onClose={() => setShowSlashPopup(false)}
          visible={showSlashPopup}
        />
        <div className="flex items-end gap-2 border border-gray-200 rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-[var(--color-primary)]/20 focus-within:border-[var(--color-primary)]">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="Send a message..."
            rows={1}
            className="flex-1 resize-none text-sm outline-none bg-transparent max-h-[150px]"
          />
          <button
            disabled={!input.trim() || isStreaming}
            onClick={handleSend}
            className="p-1.5 rounded-lg bg-[var(--color-primary)] text-white disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity shrink-0"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
