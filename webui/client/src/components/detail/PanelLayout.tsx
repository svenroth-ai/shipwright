import type { ReactNode } from 'react';
import { usePanelResize } from '../../hooks/usePanelResize';
import { DragHandle } from './DragHandle';

interface PanelLayoutProps {
  leftPanel: ReactNode;
  rightPanel: ReactNode;
}

export function PanelLayout({ leftPanel, rightPanel }: PanelLayoutProps) {
  const { leftPercent, isDragging, handleMouseDown, containerRef } = usePanelResize('task-detail-panels', 60);

  return (
    <div ref={containerRef} className="flex flex-1 overflow-hidden" data-testid="panel-layout">
      <div
        className={`overflow-hidden ${isDragging ? 'pointer-events-none' : ''}`}
        style={{ width: `${leftPercent}%` }}
      >
        {leftPanel}
      </div>
      <DragHandle onMouseDown={handleMouseDown} isDragging={isDragging} />
      <div
        className={`overflow-hidden ${isDragging ? 'pointer-events-none' : ''}`}
        style={{ width: `${100 - leftPercent}%` }}
      >
        {rightPanel}
      </div>
    </div>
  );
}
