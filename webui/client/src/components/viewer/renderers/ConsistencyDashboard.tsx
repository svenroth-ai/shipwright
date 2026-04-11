import { useMemo } from 'react';
import type { RendererProps } from '../../../types/viewer';

interface ConsistencyCategory {
  category: string;
  status: 'pass' | 'warn' | 'fail';
  details: string;
}

const STATUS_STYLES: Record<string, string> = {
  pass: 'bg-green-100 text-green-700',
  warn: 'bg-amber-100 text-amber-700',
  fail: 'bg-red-100 text-red-700',
};

export function ConsistencyDashboard({ content }: RendererProps) {
  const categories = useMemo<ConsistencyCategory[]>(() => {
    try {
      const parsed = JSON.parse(content);
      return parsed.categories ?? parsed ?? [];
    } catch {
      return [];
    }
  }, [content]);

  if (categories.length === 0) {
    return <div className="p-4 text-sm text-gray-400">No consistency data found</div>;
  }

  return (
    <div className="p-4 overflow-auto h-full" data-testid="consistency-dashboard">
      <h2 className="text-sm font-semibold mb-3">Consistency Report</h2>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-gray-50">
            <th className="text-left px-3 py-2 font-medium text-gray-600">Category</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Status</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Details</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((cat, i) => (
            <tr key={i} className="border-t border-gray-100">
              <td className="px-3 py-2">{cat.category}</td>
              <td className="px-3 py-2">
                <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${STATUS_STYLES[cat.status] ?? 'bg-gray-100 text-gray-600'}`}>
                  {cat.status}
                </span>
              </td>
              <td className="px-3 py-2 text-gray-500">{cat.details}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
