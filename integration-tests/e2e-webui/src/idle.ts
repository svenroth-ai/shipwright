// Idle abort: no change in the progress snapshot for `idleMs` means the run is stuck (typically on a
// prompt this spec cannot answer). The snapshot is any string: phase and task states plus terminal text.
export const IDLE_MINUTES = 20;

export class IdleWatch {
  private last = "";
  private changedAt: number;

  constructor(
    private readonly idleMs: number,
    private readonly now: () => number = Date.now,
  ) {
    this.changedAt = now();
  }

  /** Feed the current snapshot; returns true while the run still shows progress. */
  observe(snapshot: string): boolean {
    if (snapshot !== this.last) {
      this.last = snapshot;
      this.changedAt = this.now();
    }
    return !this.idle();
  }

  idle(): boolean {
    return this.now() - this.changedAt >= this.idleMs;
  }
}
