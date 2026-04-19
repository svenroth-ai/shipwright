import { useMutation, useQueryClient } from "@tanstack/react-query";
import { forkTask, launchTask, type CopyCommandForms, type ExternalTask } from "../lib/externalApi";

export function useLaunchTask() {
  const qc = useQueryClient();
  return useMutation<
    { task: ExternalTask; commands: CopyCommandForms },
    Error,
    { taskId: string; resume?: boolean }
  >({
    mutationFn: ({ taskId, resume }) => launchTask(taskId, { resume }),
    onSuccess: ({ task }) => {
      qc.setQueryData(["external-task", task.taskId], task);
      void qc.invalidateQueries({ queryKey: ["external-tasks"] });
    },
  });
}

export function useForkTask() {
  const qc = useQueryClient();
  return useMutation<
    { task: ExternalTask; commands: CopyCommandForms },
    Error,
    { taskId: string; title?: string }
  >({
    mutationFn: ({ taskId, title }) => forkTask(taskId, { title }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["external-tasks"] });
    },
  });
}
