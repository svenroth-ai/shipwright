interface FileReferencePopupProps {
  query: string;
  onSelect: (filePath: string) => void;
  onClose: () => void;
  visible: boolean;
}

// Placeholder — actual file list fetched from API in Split 03
export function FileReferencePopup({ query, onSelect, onClose, visible }: FileReferencePopupProps) {
  if (!visible) return null;

  return (
    <div className="absolute bottom-full left-0 mb-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto w-72 z-50">
      <div className="px-3 py-4 text-center text-xs text-gray-400">
        File browser — available after Split 03
      </div>
      {/* Suppress unused var warnings */}
      <span className="hidden">{query}{String(onSelect)}{String(onClose)}</span>
    </div>
  );
}
