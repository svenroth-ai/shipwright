/**
 * Deterministic messages for `http.Server` bind failures.
 *
 * Hono's `@hono/node-server` returns the underlying `http.Server`; attach
 * an `error` listener and pipe the error through this formatter so the
 * operator sees a consistent, actionable line regardless of which errno
 * tripped. EADDRINUSE gets a special hint about parallel worktrees;
 * other bind errors stay loud but distinct.
 *
 * No probe, no retry. A probe-then-bind would be TOCTOU-racy on Windows
 * where ephemeral ports recycle fast.
 */

export interface BindErrorFormat {
  message: string;
  exitCode: number;
}

interface NodeBindError extends Error {
  code?: string;
}

export function formatBindError(
  err: unknown,
  port: number,
): BindErrorFormat {
  const e = (err ?? new Error("unknown bind error")) as NodeBindError;
  const code = e.code ?? "";
  const detail = e.message && e.message.trim().length > 0 ? e.message : "no detail";

  switch (code) {
    case "EADDRINUSE":
      return {
        message:
          `Port ${port} is in use. Override via PORT=<other> or stop the ` +
          `existing process (e.g. "npm run dev:fresh" or netstat/taskkill).`,
        exitCode: 1,
      };
    case "EACCES":
      return {
        message:
          `Port ${port}: permission denied (low-numbered ports require ` +
          `elevation). Use a port ≥ 1024 or run as an administrator.`,
        exitCode: 1,
      };
    case "EADDRNOTAVAIL":
      return {
        message:
          `Port ${port}: address not available. Check that the host you ` +
          `asked to bind to exists on this machine.`,
        exitCode: 1,
      };
    default:
      return {
        message: `Failed to bind port ${port}: ${detail}${code ? ` (${code})` : ""}`,
        exitCode: 1,
      };
  }
}
