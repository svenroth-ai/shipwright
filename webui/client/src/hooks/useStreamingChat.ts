import { useState, useRef, useEffect } from 'react';

export function useStreamingChat() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [displayContent, setDisplayContent] = useState('');
  const bufferRef = useRef('');

  useEffect(() => {
    if (!isStreaming) return;
    const interval = setInterval(() => {
      if (bufferRef.current) {
        setDisplayContent((prev) => prev + bufferRef.current);
        bufferRef.current = '';
      }
    }, 100);
    return () => clearInterval(interval);
  }, [isStreaming]);

  function appendToken(token: string) {
    bufferRef.current += token;
  }

  function startStream() {
    setIsStreaming(true);
    setDisplayContent('');
    bufferRef.current = '';
  }

  function endStream() {
    // Flush remaining buffer
    if (bufferRef.current) {
      setDisplayContent((prev) => prev + bufferRef.current);
      bufferRef.current = '';
    }
    setIsStreaming(false);
  }

  return { isStreaming, displayContent, appendToken, startStream, endStream };
}
