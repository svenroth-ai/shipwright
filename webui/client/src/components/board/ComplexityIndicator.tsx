const COMPLEXITY_STYLES: Record<string, string> = {
  low: 'text-green-600',
  medium: 'text-amber-600',
  high: 'text-red-600',
};

interface ComplexityIndicatorProps {
  complexity?: string;
}

export function ComplexityIndicator({ complexity }: ComplexityIndicatorProps) {
  if (!complexity) return null;

  const style = COMPLEXITY_STYLES[complexity] ?? 'text-gray-500';

  return (
    <span className={`text-[10px] font-medium capitalize ${style}`}>
      {complexity}
    </span>
  );
}
