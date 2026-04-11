import { Terminal, FileText, Search, Pencil, FileEdit, Wrench } from 'lucide-react';

const TOOL_ICONS: Record<string, typeof Terminal> = {
  Bash: Terminal,
  Read: FileText,
  Grep: Search,
  Edit: Pencil,
  Write: FileEdit,
};

interface ToolIconProps {
  toolName: string;
}

export function ToolIcon({ toolName }: ToolIconProps) {
  const Icon = TOOL_ICONS[toolName] ?? Wrench;
  return <Icon size={16} className="text-gray-400 shrink-0" />;
}
