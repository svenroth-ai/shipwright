import type { FileTreeNode } from '../../hooks/useFileTree';
import { TreeNode } from './TreeNode';

interface DirectoryTreeProps {
  nodes: FileTreeNode[];
  onFileClick: (filePath: string) => void;
}

export function DirectoryTree({ nodes, onFileClick }: DirectoryTreeProps) {
  return (
    <div className="py-2" data-testid="directory-tree">
      {nodes.map((node) => (
        <TreeNode key={node.path} node={node} depth={0} onFileClick={onFileClick} />
      ))}
    </div>
  );
}
