import { useTurnStatusStore, taskKeyOf, type TurnAssembly } from '../stores/turnStatusStore';

const IDLE: TurnAssembly = { status: 'idle', lastEventAt: 0, watchdogStale: false };

/**
 * Read the per-task turn assembly slot. Returns IDLE for unknown tasks so
 * ChatPanel can call this unconditionally without an explicit ensure().
 *
 * Relies on Zustand's default shallow comparison on the returned reference.
 * Since slots are immutable (every setter in turnStatusStore creates a new
 * TurnAssembly object), referential equality is sufficient.
 */
export function useTurnStatus(projectId: string, taskId: string): TurnAssembly {
  const taskKey = taskKeyOf(projectId, taskId);
  return useTurnStatusStore((state) => state.byTask[taskKey] ?? IDLE);
}
