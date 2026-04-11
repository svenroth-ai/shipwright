import { useState, useCallback, useEffect, useRef } from 'react';
import { useLocalStorage } from './useLocalStorage';

export function usePanelResize(storageKey: string, defaultLeftPercent: number) {
  const [savedPercent, setSavedPercent] = useLocalStorage(storageKey, defaultLeftPercent);
  const [leftPercent, setLeftPercent] = useState(savedPercent);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      let percent = (x / rect.width) * 100;
      percent = Math.max(30, Math.min(80, percent));
      setLeftPercent(percent);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.body.style.userSelect = '';
      setLeftPercent((current) => {
        setSavedPercent(current);
        return current;
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
    };
  }, [isDragging, setSavedPercent]);

  return { leftPercent, isDragging, handleMouseDown, containerRef };
}
