import { useState, useEffect, useRef } from 'react';
import { shouldSkipClassification } from '../lib/intentGuards';
import { apiPost } from '../lib/api';

interface IntentResult {
  intent: string;
  confidence: number;
}

export function useIntentDetection(projectId: string, message: string) {
  const [hint, setHint] = useState<IntentResult | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setHint(null);

    if (!message.trim() || shouldSkipClassification(message)) {
      setIsDetecting(false);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);

    debounceRef.current = setTimeout(async () => {
      setIsDetecting(true);
      try {
        const result = await apiPost<IntentResult>(`/projects/${projectId}/classify`, {
          text: message,
          mode: 'intent-only',
        });
        if (result.confidence >= 0.7) {
          setHint(result);
        } else {
          setHint(null);
        }
      } catch {
        setHint(null);
      } finally {
        setIsDetecting(false);
      }
    }, 500);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [projectId, message]);

  return { hint, isDetecting };
}
