import { GripVertical } from 'lucide-react';

interface DragHandleProps {
  onMouseDown: (e: React.MouseEvent) => void;
  isDragging: boolean;
}

export function DragHandle({ onMouseDown, isDragging }: DragHandleProps) {
  return (
    <div
      className={`w-1.5 cursor-col-resize flex items-center justify-center transition-colors shrink-0 ${
        isDragging ? 'bg-[var(--color-primary)]/30' : 'hover:bg-[var(--color-primary)]/20'
      }`}
      onMouseDown={onMouseDown}
      role="separator"
      aria-orientation="vertical"
    >
      <GripVertical size={14} className="text-gray-300" />
    </div>
  );
}
