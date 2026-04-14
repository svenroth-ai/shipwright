import { useState, useRef } from 'react';
import { Send, Paperclip, X } from 'lucide-react';
import { ChatToolbar } from './ChatToolbar';
import { SlashCommandPopup } from './SlashCommandPopup';
import { useChatSettings } from '../../hooks/useChatSettings';
import { readFileAsBase64, type ImageAttachment } from '../../lib/image';
import type { AutonomyOption } from '../../types/settings';

export interface ChatSendPayload {
  message: string;
  images?: Array<{ media_type: string; data: string }>;
  model: string;
  mode: string;
  autonomy: string;
}

interface ChatInputProps {
  onSend: (payload: ChatSendPayload) => void;
  isStreaming: boolean;
  autonomy: AutonomyOption;
  /** Iterate 10 — when present, PermissionMode fires the mid-task
   *  mode-switch mutation instead of just updating localStorage. */
  projectId?: string;
  taskId?: string;
}

export function ChatInput({ onSend, isStreaming, autonomy, projectId, taskId }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [showSlashPopup, setShowSlashPopup] = useState(false);
  const [slashQuery, setSlashQuery] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const settings = useChatSettings();

  function handleSend() {
    const trimmed = input.trim();
    if ((!trimmed && images.length === 0) || isStreaming) return;
    onSend({
      message: trimmed,
      ...(images.length > 0
        ? { images: images.map((img) => ({ media_type: img.mediaType, data: img.base64 })) }
        : {}),
      model: settings.model,
      mode: settings.mode,
      autonomy,
    });
    setInput('');
    setImages([]);
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

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files) return;
    const newImages: ImageAttachment[] = [];
    for (const file of Array.from(files)) {
      if (!file.type.startsWith('image/')) continue;
      const { base64, mediaType } = await readFileAsBase64(file);
      newImages.push({ name: file.name, base64, mediaType });
    }
    setImages((prev) => [...prev, ...newImages]);
    e.target.value = '';
  }

  async function handlePaste(e: React.ClipboardEvent) {
    const items = e.clipboardData?.items;
    if (!items) return;
    const newImages: ImageAttachment[] = [];
    for (const item of Array.from(items)) {
      if (!item.type.startsWith('image/')) continue;
      const file = item.getAsFile();
      if (!file) continue;
      const { base64, mediaType } = await readFileAsBase64(file);
      newImages.push({
        name: `pasted-${Date.now()}.${file.type.split('/')[1]}`,
        base64,
        mediaType,
      });
    }
    if (newImages.length > 0) {
      e.preventDefault();
      setImages((prev) => [...prev, ...newImages]);
    }
  }

  function removeImage(index: number) {
    setImages((prev) => prev.filter((_, i) => i !== index));
  }

  const canSend = (input.trim().length > 0 || images.length > 0) && !isStreaming;

  return (
    <div className="border-t border-[var(--color-border,#e0dbd4)] bg-white pt-2 pb-4">
      <ChatToolbar
        model={settings.model}
        setModel={settings.setModel}
        mode={settings.mode}
        setMode={settings.setMode}
        autonomy={autonomy}
        projectId={projectId}
        taskId={taskId}
      />

      {/* Image thumbnails */}
      {images.length > 0 && (
        <div className="px-3 pt-2 flex items-center gap-2 flex-wrap">
          {images.map((img, i) => (
            <div key={i} className="relative group">
              <img
                src={`data:${img.mediaType};base64,${img.base64}`}
                alt={img.name}
                className="w-12 h-12 rounded-lg object-cover border border-[var(--color-border,#e0dbd4)]"
              />
              <button
                onClick={() => removeImage(i)}
                aria-label="Remove image"
                className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-gray-900 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="relative px-3 pt-2 pb-1">
        <SlashCommandPopup
          query={slashQuery}
          onSelect={handleSlashSelect}
          onClose={() => setShowSlashPopup(false)}
          visible={showSlashPopup}
        />
        <div className="flex items-end gap-2 border border-[var(--color-border,#e0dbd4)] rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-[var(--color-primary)]/20 focus-within:border-[var(--color-primary)]">
          {/* Image upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleFileSelect}
            className="hidden"
            aria-label="Attach images"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title="Attach image (or paste from clipboard)"
            className="p-1.5 rounded-lg text-gray-500 hover:text-[var(--color-primary)] hover:bg-[var(--color-muted-bg,#ede8e1)] transition-colors shrink-0"
          >
            <Paperclip size={16} />
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder="Send a message or paste an image..."
            rows={1}
            className="flex-1 resize-none text-sm outline-none bg-transparent max-h-[150px]"
          />
          <button
            disabled={!canSend}
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
