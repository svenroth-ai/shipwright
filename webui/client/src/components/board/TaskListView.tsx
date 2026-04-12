import { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import type { Task } from '../../types';
import { TaskListRow } from './TaskListRow';

type SortField = 'title' | 'phase' | 'priority' | 'updated';
type SortDir = 'asc' | 'desc';

const PRIORITY_ORDER: Record<string, number> = { P1: 0, P2: 1, P3: 2 };

interface TaskListViewProps {
  tasks: Task[];
}

export function TaskListView({ tasks }: TaskListViewProps) {
  const [sortField, setSortField] = useState<SortField>('updated');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const sorted = useMemo(() => {
    const arr = [...tasks];
    arr.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'title':
          cmp = a.title.localeCompare(b.title);
          break;
        case 'phase':
          cmp = (a.currentPhase ?? '').localeCompare(b.currentPhase ?? '');
          break;
        case 'priority':
          cmp = (PRIORITY_ORDER[a.priority ?? ''] ?? 9) - (PRIORITY_ORDER[b.priority ?? ''] ?? 9);
          break;
        case 'updated':
          cmp = new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [tasks, sortField, sortDir]);

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  }

  function SortHeader({ field, label }: { field: SortField; label: string }) {
    const isActive = sortField === field;
    return (
      <th
        className="py-2.5 px-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 select-none"
        onClick={() => handleSort(field)}
      >
        <span className="flex items-center gap-1">
          {label}
          {isActive && (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
        </span>
      </th>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <table className="w-full border-collapse">
        <thead className="bg-gray-50">
          <tr>
            <th className="py-2.5 px-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-10">
              Status
            </th>
            <SortHeader field="title" label="Title" />
            <SortHeader field="phase" label="Phase" />
            <SortHeader field="priority" label="Priority" />
            <th className="py-2.5 px-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Tests
            </th>
            <th className="py-2.5 px-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Commit
            </th>
            <SortHeader field="updated" label="Updated" />
            <th className="py-2.5 px-2 w-8" />
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={8} className="py-8 text-center text-sm text-gray-400">
                No tasks match current filters
              </td>
            </tr>
          ) : (
            sorted.map((task) => <TaskListRow key={task.id} task={task} />)
          )}
        </tbody>
      </table>
    </div>
  );
}
