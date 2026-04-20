import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  closeTask,
  createTask,
  deleteTask,
  getTask,
  listTasks,
  renameTask,
  type ExternalTask,
} from "../lib/externalApi";

const LIST_KEY = ["external-tasks"] as const;
const detailKey = (taskId: string) => ["external-task", taskId] as const;

/**
 * List external tasks, optionally filtered by projectId (section 02).
 *
 * Passing `null` or omitting the arg = All Projects. Passing the reserved
 * literal "unassigned" narrows to the synthesized bucket. The query key
 * includes projectId so switching filters produces a fresh fetch without
 * stale overlap.
 */
export function useExternalTasks(args: { projectId?: string | null } = {}) {
  const projectId = args.projectId ?? null;
  return useQuery<ExternalTask[]>({
    queryKey: [...LIST_KEY, projectId] as const,
    queryFn: () => listTasks({ projectId }),
    refetchInterval: 2_000,
    refetchIntervalInBackground: false,
  });
}

export function useExternalTask(taskId: string | undefined) {
  return useQuery<ExternalTask>({
    queryKey: taskId ? detailKey(taskId) : ["external-task", "none"],
    queryFn: () => getTask(taskId!),
    enabled: Boolean(taskId),
  });
}

export function useCreateExternalTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createTask,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export function useCloseExternalTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: closeTask,
    onSuccess: (task) => {
      qc.setQueryData(detailKey(task.taskId), task);
      void qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export function useRenameTask() {
  const qc = useQueryClient();
  return useMutation<ExternalTask, Error, { taskId: string; title: string }>({
    mutationFn: ({ taskId, title }) => renameTask(taskId, title),
    onSuccess: (task) => {
      qc.setQueryData(detailKey(task.taskId), task);
      void qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export function useDeleteExternalTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}
