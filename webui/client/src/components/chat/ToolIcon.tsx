import { Terminal, FileText, Search, Pencil, FileEdit, Wrench, FolderSearch, Globe, Bot, ListTodo, Notebook } from 'lucide-react';
import type { ComponentType } from 'react';

type IconComponent = ComponentType<{ size?: number; className?: string }>;

interface TileStyle {
  icon: IconComponent;
  bg: string;
  fg: string;
}

/**
 * Tool → tile style mapping matching mockup 11-task-detail.html:
 *   .tool-icon.read  { background: #DBEAFE; color: #2563EB; }  (blue)
 *   .tool-icon.edit  { background: #FEF3C7; color: #D97706; }  (amber)
 *   .tool-icon.bash  { background: #D1FAE5; color: #059669; }  (green)
 */
const TOOL_STYLES: Record<string, TileStyle> = {
  Read:        { icon: FileText,    bg: '#DBEAFE', fg: '#2563EB' },
  Glob:        { icon: FolderSearch,bg: '#DBEAFE', fg: '#2563EB' },
  Grep:        { icon: Search,      bg: '#DBEAFE', fg: '#2563EB' },
  Edit:        { icon: Pencil,      bg: '#FEF3C7', fg: '#D97706' },
  Write:       { icon: FileEdit,    bg: '#FEF3C7', fg: '#D97706' },
  NotebookEdit:{ icon: Notebook,    bg: '#FEF3C7', fg: '#D97706' },
  Bash:        { icon: Terminal,    bg: '#D1FAE5', fg: '#059669' },
  WebFetch:    { icon: Globe,       bg: '#E0E7FF', fg: '#4F46E5' },
  WebSearch:   { icon: Globe,       bg: '#E0E7FF', fg: '#4F46E5' },
  Agent:       { icon: Bot,         bg: '#F3E8FF', fg: '#9333EA' },
  Task:        { icon: Bot,         bg: '#F3E8FF', fg: '#9333EA' },
  TodoWrite:   { icon: ListTodo,    bg: '#FCE7F3', fg: '#DB2777' },
};

const DEFAULT_STYLE: TileStyle = { icon: Wrench, bg: '#F3F4F6', fg: '#6B7280' };

interface Props {
  toolName: string;
}

/**
 * Colored tile icon (24×24 rounded square with SVG inside).
 * Matches mockup .tool-icon styling.
 */
export function ToolIconTile({ toolName }: Props) {
  const style = TOOL_STYLES[toolName] ?? DEFAULT_STYLE;
  const Icon = style.icon;
  return (
    <div
      className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0"
      style={{ background: style.bg, color: style.fg }}
    >
      <Icon size={13} />
    </div>
  );
}

/** Legacy plain icon (kept for backward compatibility with any stray imports). */
export function ToolIcon({ toolName }: Props) {
  const style = TOOL_STYLES[toolName] ?? DEFAULT_STYLE;
  const Icon = style.icon;
  return <Icon size={16} className="text-gray-400 shrink-0" />;
}
