import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { MoreHorizontal } from 'lucide-react';

interface CardOverflowMenuProps {
  onClose: () => void;
  onCancel: () => void;
}

export function CardOverflowMenu({ onClose, onCancel }: CardOverflowMenuProps) {
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
          className="bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[120px] z-50"
          sideOffset={4}
          onClick={(e) => e.stopPropagation()}
        >
          <DropdownMenu.Item
            className="px-3 py-1.5 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 outline-none"
            onSelect={onClose}
          >
            Close
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className="px-3 py-1.5 text-sm text-red-600 cursor-pointer hover:bg-red-50 outline-none"
            onSelect={onCancel}
          >
            Cancel
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
