import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  closeTask,
  createTask,
  deleteTask,
  getTask,
  listTasks,
  type ExternalTask,
} from "../lib/externalApi";

const LIST_KEY = ["external-tasks"] as const;
const detailKey = (taskId: string) => ["external-task", taskId] as const;

export function useExternalTasks() {
  return useQuery<ExternalTask[]>({
    queryKey: LIST_KEY,
    queryFn: listTasks,
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

export function useDeleteExternalTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}
