import { memo, useMemo } from 'react';
import type { RendererProps } from '../../../types/viewer';

const EXT_TO_LANG: Record<string, string> = {
  ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx',
  py: 'python', css: 'css', sql: 'sql', sh: 'bash',
  yaml: 'yaml', yml: 'yaml', toml: 'toml', json: 'json',
  html: 'html', md: 'markdown',
};

function getLang(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
  return EXT_TO_LANG[ext] ?? 'plaintext';
}

export const CodeRenderer = memo(function CodeRenderer({ tab, content }: RendererProps) {
  const lines = useMemo(() => content.split('\n'), [content]);
  const lang = getLang(tab.filePath);

  return (
    <div className="h-full overflow-auto bg-gray-900 text-gray-100 font-mono text-sm" data-testid="code-renderer">
      <div className="px-2 py-1 text-xs text-gray-500 border-b border-gray-700">
        {tab.label} — {lang}
      </div>
      <pre className="p-0 m-0">
        <code className={`language-${lang}`}>
          {lines.map((line, i) => (
            <div key={i} className="flex hover:bg-gray-800/50">
              <span className="select-none w-12 text-right pr-4 text-gray-600 shrink-0">
                {i + 1}
              </span>
              <span className="flex-1 whitespace-pre-wrap break-all">{line || ' '}</span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
});
