export type FileType =
  | 'markdown'
  | 'html'
  | 'code'
  | 'json'
  | 'spec'
  | 'plan'
  | 'consistency'
  | 'compliance'
  | 'url'
  | 'unknown';

export interface ViewerTab {
  id: string;
  label: string;
  filePath: string;
  fileType: FileType;
  projectId: string;
}

export interface RendererProps {
  tab: ViewerTab;
  content: string;
  projectId: string;
}

export function resolveFileType(filePath: string): FileType {
  if (filePath.startsWith('http://') || filePath.startsWith('https://')) return 'url';

  const lower = filePath.toLowerCase();

  if (lower.endsWith('.md')) {
    if (lower.includes('compliance/')) return 'compliance';
    if (lower.endsWith('spec.md')) return 'spec';
    if (lower.endsWith('plan.md')) return 'plan';
    return 'markdown';
  }

  if (lower.endsWith('.html') && lower.includes('designs/')) return 'html';

  if (/\.(ts|tsx|js|jsx|css|py|sql|sh|yaml|yml|toml)$/.test(lower)) return 'code';

  if (lower.endsWith('.json')) {
    if (lower.includes('consistency_report')) return 'consistency';
    return 'json';
  }

  return 'unknown';
}
