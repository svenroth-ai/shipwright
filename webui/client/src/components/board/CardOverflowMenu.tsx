import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { MoreHorizontal, CheckCircle, Pencil, Trash2 } from 'lucide-react';

interface CardOverflowMenuProps {
  onClose: () => void;
  onDelete: () => void;
  onEdit?: () => void;
}

export function CardOverflowMenu({ onClose, onDelete, onEdit }: CardOverflowMenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          aria-label="Task actions"
          className="p-1 rounded hover:bg-gray-100 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal size={16} className="text-gray-400" />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="bg-white rounded-lg shadow-lg border border-[#e0dbd4] py-1 min-w-[130px] z-50"
          sideOffset={4}
          onClick={(e) => e.stopPropagation()}
        >
          {onEdit && (
            <>
              <DropdownMenu.Item
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 outline-none"
                onSelect={onEdit}
              >
                <Pencil size={14} /> Edit task
              </DropdownMenu.Item>
              <DropdownMenu.Separator className="h-px bg-gray-100 my-1" />
            </>
          )}
          <DropdownMenu.Item
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 outline-none"
            onSelect={onClose}
          >
            <CheckCircle size={14} /> Close
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="h-px bg-gray-100 my-1" />
          <DropdownMenu.Item
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-red-600 cursor-pointer hover:bg-red-50 outline-none"
            onSelect={onDelete}
          >
            <Trash2 size={14} /> Delete
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
