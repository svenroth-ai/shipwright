/*
 * useReassignTask — TanStack Query mutation for PATCH
 * /api/external/tasks/:id with `{projectId}` (iterate 3 section 04 +
 * follow-through on section 02 FR-03.03).
 *
 * Optimistic update + rollback: on mutate, we patch the in-cache task so
 * the project chip re-renders instantly; on error, we rollback to the
 * previous snapshot. The cache is the source of truth so every consumer
 * (TaskDetail header, TaskBoard, Inbox) sees the change in the same frame.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { assignTaskProject, type ExternalTask } from "../lib/externalApi";

const TASK_LIST_KEY = ["external-tasks"] as const;
const taskDetailKey = (taskId: string) => ["external-task", taskId] as const;

interface Variables {
  taskId: string;
  projectId: string;
}

interface Context {
  prevDetail: ExternalTask | undefined;
  prevLists: Array<readonly [readonly unknown[], ExternalTask[] | undefined]>;
}

export function useReassignTask() {
  const qc = useQueryClient();
  return useMutation<ExternalTask, Error, Variables, Context>({
    mutationFn: ({ taskId, projectId }) => assignTaskProject(taskId, projectId),
    onMutate: async ({ taskId, projectId }) => {
      await qc.cancelQueries({ queryKey: taskDetailKey(taskId) });
      await qc.cancelQueries({ queryKey: TASK_LIST_KEY });

      const prevDetail = qc.getQueryData<ExternalTask>(taskDetailKey(taskId));
      if (prevDetail) {
        qc.setQueryData(taskDetailKey(taskId), { ...prevDetail, projectId });
      }

      // The list query is keyed as ["external-tasks", projectIdFilter]; we
      // patch every cached list snapshot so the header chip change is
      // reflected without waiting for refetch.
      const prevLists = qc.getQueriesData<ExternalTask[]>({
        queryKey: TASK_LIST_KEY,
      });
      for (const [key, list] of prevLists) {
        if (!list) continue;
        qc.setQueryData(
          key,
          list.map((t) => (t.taskId === taskId ? { ...t, projectId } : t)),
        );
      }

      return { prevDetail, prevLists };
    },
    onError: (_err, vars, ctx) => {
      if (!ctx) return;
      if (ctx.prevDetail) {
        qc.setQueryData(taskDetailKey(vars.taskId), ctx.prevDetail);
      }
      for (const [key, list] of ctx.prevLists) {
        qc.setQueryData(key, list);
      }
    },
    onSuccess: (task) => {
      qc.setQueryData(taskDetailKey(task.taskId), task);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: TASK_LIST_KEY });
    },
  });
}
