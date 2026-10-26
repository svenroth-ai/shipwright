// One idempotent shutdown path for every exit: normal end, error, abort, SIGINT/SIGTERM/SIGBREAK, process exit.
// Steps are synchronous (the only thing an exit handler can rely on) and run in order; one failing step never
// stops the next, so the copied login is deleted even if killing the server or writing the report throws.
export class Shutdown {
  private done = false;
  private readonly steps: (() => void)[] = [];
  private detach: (() => void) | null = null;

  add(step: () => void): void {
    this.steps.push(step);
  }

  /** Runs all steps once; later calls do nothing. Returns the number of steps that threw. */
  run(): number {
    if (this.done) return 0;
    this.done = true;
    let failed = 0;
    for (const step of this.steps) {
      try {
        step();
      } catch {
        failed += 1;
      }
    }
    return failed;
  }

  /** Route signals and process exit into run(). */
  install(): void {
    const onSignal = (signal: NodeJS.Signals) => {
      this.run();
      process.exit(signal === "SIGINT" ? 130 : 143);
    };
    const onExit = () => void this.run();
    const signals: NodeJS.Signals[] = ["SIGINT", "SIGTERM", "SIGBREAK"];
    for (const s of signals) process.on(s, onSignal);
    process.on("exit", onExit);
    this.detach = () => {
      for (const s of signals) process.off(s, onSignal);
      process.off("exit", onExit);
    };
  }

  uninstall(): void {
    this.detach?.();
    this.detach = null;
  }
}
