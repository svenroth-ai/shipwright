import { useState } from 'react';
import { ChevronRight, File, Folder } from 'lucide-react';
import type { FileTreeNode } from '../../hooks/useFileTree';
import { GitStatusBadge } from './GitStatusBadge';

interface TreeNodeProps {
  node: FileTreeNode;
  depth: number;
  onFileClick: (filePath: string) => void;
}

export function TreeNode({ node, depth, onFileClick }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(depth === 0);
  const isDir = node.type === 'directory';

  return (
    <div>
      <button
        className="flex items-center gap-1.5 w-full text-left py-1 px-2 hover:bg-gray-100 rounded text-xs"
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={() => isDir ? setExpanded(!expanded) : onFileClick(node.path)}
      >
        {isDir ? (
          <ChevronRight
            size={12}
            className={`text-gray-400 transition-transform shrink-0 ${expanded ? 'rotate-90' : ''}`}
          />
        ) : (
          <span className="w-3" />
        )}
        {isDir ? (
          <Folder size={14} className="text-amber-500 shrink-0" />
        ) : (
          <File size={14} className="text-gray-400 shrink-0" />
        )}
        <span className="flex-1 truncate">{node.name}</span>
        <GitStatusBadge status={node.gitStatus} />
      </button>
      {isDir && expanded && node.children?.map((child) => (
        <TreeNode key={child.path} node={child} depth={depth + 1} onFileClick={onFileClick} />
      ))}
    </div>
  );
}
