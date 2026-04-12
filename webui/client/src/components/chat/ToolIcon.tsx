import { Terminal, FileText, Search, Pencil, FileEdit, Wrench, FolderSearch, Globe, Bot, ListTodo, Notebook } from 'lucide-react';

const TOOL_ICONS: Record<string, typeof Terminal> = {
  Bash: Terminal,
  Read: FileText,
  Grep: Search,
  Edit: Pencil,
  Write: FileEdit,
  Glob: FolderSearch,
  WebFetch: Globe,
  WebSearch: Globe,
  Agent: Bot,
  TodoWrite: ListTodo,
  NotebookEdit: Notebook,
};

interface ToolIconProps {
  toolName: string;
}

export function ToolIcon({ toolName }: ToolIconProps) {
  const Icon = TOOL_ICONS[toolName] ?? Wrench;
  return <Icon size={16} className="text-gray-400 shrink-0" />;
}
