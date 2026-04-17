import type { ChildProcess } from "child_process";
import type { Readable } from "stream";
import path from "path";
import fs from "fs";
import type { NdjsonMessage } from "../../../client/src/types/chat.js";
import { parseNdjsonLine } from "./ndjson-parser.js";
import { AppError } from "../middleware/error-handler.js";

export type ProcessState = "spawning" | "running" | "exited";

export interface ClaudeProcess {
  pid: number;
  taskId: string;
  projectId: string;
  sessionId: string;
  /**
   * The REAL session id reported by Claude Code CLI in its first
   * `system/init` NDJSON event. Captured lazily by readLines. Iterate 10
   * uses this as the `--resume` argument for mid-task mode switches —
   * our own UUID from `--session-id` is NOT resumable (ADR-009).
   */
  claudeSessionId?: string;
  state: ProcessState;
  exitCode?: number;
  spawnedAt: number;
  process: ChildProcess;
}

export interface SpawnDeps {
  spawn: (
    command: string,
    args: string[],
    options: { cwd: string; stdio: [string, string, string]; shell?: boolean }
  ) => ChildProcess;
}

/**
 * Claude CLI permission modes — UI-facing surface.
 *
 * Iterate 14.9 / 14.10 — `auto` is the user-facing label that mirrors the
 * VS Code extension's "Auto mode" toggle. The CLI does NOT accept
 * `--permission-mode auto`; the extension translates it to `dontAsk`
 * before spawn (verified in CLI 2.1.1: only `acceptEdits, bypassPermissions,
 * default, delegate, dontAsk, plan` are valid `--permission-mode` values).
 *
 * `auto` flows through the UI, REST payloads, settings.json, and the
 * adapter's `permissionMode` option — but {@link modeForCli} translates
 * it to `dontAsk` right before the CLI arg is appended. This keeps the
 * UI label intact while shielding the CLI from the invalid value.
 */
export type PermissionMode = "auto" | "default" | "acceptEdits" | "plan" | "bypassPermissions";

/** Concrete `--permission-mode` argument values that Claude CLI 2.1.1
 *  actually accepts. `auto` is never sent — see {@link modeForCli}. */
export type CliPermissionMode = "default" | "acceptEdits" | "plan" | "bypassPermissions" | "dontAsk";

/**
 * Translate a UI-facing PermissionMode (or undefined) to the concrete
 * value that goes after `--permission-mode` on the CLI. `auto` and
 * `undefined` both resolve to `dontAsk` (matches the VS Code extension's
 * Auto mode behaviour). Everything else passes through verbatim.
 *
 * Exported so route-level callsites can log both `uiMode` and `cliMode`
 * in the `claude.spawn` event without re-implementing the mapping.
 */
export function modeForCli(mode: PermissionMode | string | undefined): CliPermissionMode {
  if (mode === undefined || mode === "auto") return "dontAsk";
  return mode as CliPermissionMode;
}

/**
 * Claude CLI `--model` value.
 *
 * The CLI accepts BOTH the coarse alias (`opus`/`sonnet`/`haiku` — picks the
 * latest stable in that family) AND a concrete id (`claude-opus-4-7`,
 * `claude-sonnet-4-6-20251101`, etc.). Verified via `claude --help`:
 *   "--model <model>  Provide an alias for the latest model (e.g. 'sonnet'
 *    or 'opus') or a model's full name (e.g. 'claude-sonnet-4-5-20250929')."
 *
 * Iterate 14.13 — switched from a narrow `"opus" | "sonnet" | "haiku"` union
 * to `string` because the alias loses version specificity. When the user
 * picks "Opus 4.7" in the dropdown but we sent `opus`, the CLI defaulted to
 * whatever it considers the latest stable opus (4.5 / 4.6 in CLI 2.1.1) and
 * the system/init reported the wrong version — closing the loop on the user's
 * selection. Now the concrete id flows through verbatim.
 *
 * The legacy `ModelAlias` export is retained for callers that want an
 * explicit narrow type but it is no longer required by `ClaudeSpawnOptions`.
 */
export type ModelAlias = "opus" | "sonnet" | "haiku";

export interface ClaudeSpawnOptions {
  projectDir: string;
  projectId: string;
  taskId: string;
  sessionId?: string;
  pluginDirs: string[];
  /**
   * Initial user prompt. Will be sent as the first NDJSON "user" message
   * after spawn. Follow-ups go via sendUserMessage().
   */
  prompt: string;
  /**
   * Claude CLI permission mode — matches --permission-mode flag values.
   * Defaults to bypassPermissions which is what VS Code's extension uses.
   */
  permissionMode?: PermissionMode;
  /**
   * Claude CLI `--model` argument. Accepts EITHER a coarse family alias
   * (`opus`/`sonnet`/`haiku`) OR a concrete model id
   * (`claude-opus-4-7`, `claude-sonnet-4-6-20251101`, …) — the CLI handles
   * both forms. When undefined, the CLI picks its compiled-in default
   * (currently `claude-opus-4-5`).
   *
   * Iterate 14.13 — relaxed from `ModelAlias` to `string` so the WebUI can
   * pin the user's exact selection (Opus 4.7) instead of the alias which
   * resolves to whatever the CLI's default-stable-in-family happens to be.
   */
  model?: string;
  /**
   * When true, the `sessionId` is emitted as `--resume <id>` instead of
   * `--session-id <id>`. Used by iterate 10's mid-task mode switching:
   * after SIGTERM'ing the current process we respawn with the REAL
   * Claude session_id (captured from the previous process's system/init
   * event — see `ClaudeProcess.claudeSessionId`) to pick up the same
   * conversation with a different `--permission-mode`.
   */
  resumeSession?: boolean;
  claudeCliPath?: string;
}

/** Anthropic content-block types (subset used by sendUserMessage).
 *  `tool_result` was added in iterate 7 to unblock Claude CLI's pending
 *  AskUserQuestion call — inbox-manager sends an answer as a tool_result
 *  block referencing the stored tool_use_id. */
export type UserContentBlock =
  | { type: "text"; text: string }
  | {
      type: "image";
      source: { type: "base64"; media_type: string; data: string };
    }
  | { type: "tool_result"; tool_use_id: string; content: string };

/**
 * Resolve the Claude CLI command for the current platform.
 * On Windows, .cmd shims don't pipe stdout correctly through shell: true,
 * so we resolve the actual cli.js and run it directly with node.
 */
function resolveClaudeCommand(cliPath?: string): { command: string; prefixArgs: string[] } {
  if (cliPath) return { command: cliPath, prefixArgs: [] };

  if (process.platform === "win32") {
    const npmGlobal = process.env.APPDATA
      ? path.join(process.env.APPDATA, "npm", "node_modules", "@anthropic-ai", "claude-code", "cli.js")
      : null;
    if (npmGlobal && fs.existsSync(npmGlobal)) {
      return { command: process.execPath, prefixArgs: [npmGlobal] };
    }
  }

  return { command: "claude", prefixArgs: [] };
}

/**
 * Persistent Claude CLI process per task.
 *
 * Uses `--input-format stream-json --output-format stream-json` so the CLI
 * reads NDJSON user messages from stdin and writes NDJSON events to stdout,
 * staying alive across multiple turns. This eliminates the 5–10s cold-start
 * penalty on every follow-up message.
 *
 * Message flow:
 *   1. spawn() starts the CLI with empty placeholder prompt
 *   2. Once stdout yields the first `system/init` event, we send the initial
 *      user message as NDJSON on stdin
 *   3. sendUserMessage() can be called at any time to send follow-ups on the
 *      same pipe — no respawn, no cold start
 *   4. terminate() kills the process when the task is closed
 */
export class ClaudeAdapter {
  constructor(
    private deps: SpawnDeps,
    private onEvent: (taskId: string, msg: NdjsonMessage) => void,
    private onExit?: (taskId: string, projectId: string, exitCode: number | null) => void
  ) {}

  spawn(options: ClaudeSpawnOptions): ClaudeProcess {
    const args: string[] = [
      "--input-format", "stream-json",
      "--output-format", "stream-json",
      "--verbose",
    ];

    // Permission mode. "bypassPermissions" uses the shortcut flag
    // --dangerously-skip-permissions (what VS Code ships with). Other
    // modes use the explicit --permission-mode flag.
    //
    // Iterate 14.10 — translate UI-facing `auto` (and undefined) to the
    // CLI's `dontAsk` value via {@link modeForCli}. `auto` was never a
    // valid `--permission-mode` value; 14.9 sent it raw and every spawn
    // failed silently. The `uiMode` is preserved for the log line so
    // operators can audit the translation.
    const uiMode: PermissionMode = options.permissionMode ?? "bypassPermissions";
    const cliMode: CliPermissionMode = modeForCli(uiMode);
    if (cliMode === "bypassPermissions") {
      args.push("--dangerously-skip-permissions");
    } else {
      args.push("--permission-mode", cliMode);
    }

    for (const dir of options.pluginDirs) {
      args.push("--plugin-dir", dir);
    }

    if (options.sessionId) {
      // Iterate 10: --resume takes the REAL Claude session_id so a
      // mid-task respawn continues the same conversation under a new
      // permission-mode. --session-id is for NEW sessions tagged with
      // a UUID we pick; Claude does not let you resume by that UUID.
      if (options.resumeSession) {
        args.push("--resume", options.sessionId);
      } else {
        args.push("--session-id", options.sessionId);
      }
    }

    if (options.model) {
      args.push("--model", options.model);
    }

    // `-p` with placeholder is required when using --input-format stream-json.
    // Claude CLI still waits on stdin for actual messages.
    args.push("-p", "placeholder");

    const { command, prefixArgs } = resolveClaudeCommand(options.claudeCliPath);
    const fullArgs = [...prefixArgs, ...args];

    // Iterate 14.10 — emit a structured `claude.spawn` event with the
    // UI-facing `uiMode` and the actual `cliMode` we appended after
    // `--permission-mode`. Operators can `grep claude.spawn` in the
    // server log to confirm Auto mode is translated correctly without
    // having to dump the full args array.
    console.log(JSON.stringify({
      level: "info",
      event: "claude.spawn",
      source: "claude-adapter",
      taskId: options.taskId,
      projectId: options.projectId,
      command,
      argsCount: fullArgs.length,
      uiMode,
      cliMode,
      model: options.model,
      mode: "persistent-ndjson",
    }));

    // stdin must be piped so we can write NDJSON user messages to the CLI
    const child = this.deps.spawn(command, fullArgs, {
      cwd: options.projectDir,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const claudeProcess: ClaudeProcess = {
      pid: child.pid ?? 0,
      taskId: options.taskId,
      projectId: options.projectId,
      sessionId: options.sessionId ?? options.taskId,
      state: "spawning",
      spawnedAt: Date.now(),
      process: child,
    };

    // Queue the initial prompt; will be sent when stdin is ready
    let initialPromptSent = false;
    const sendInitialPrompt = () => {
      if (initialPromptSent) return;
      initialPromptSent = true;
      try {
        this.sendUserMessage(claudeProcess, options.prompt);
      } catch (err) {
        console.error(JSON.stringify({
          level: "error",
          source: "claude-adapter",
          taskId: options.taskId,
          message: `Initial prompt send failed: ${String(err)}`,
        }));
      }
    };

    if (child.stdout) {
      this.readLines(child.stdout, (line) => {
        if (claudeProcess.state === "spawning") {
          claudeProcess.state = "running";
          // The CLI is ready once it has produced any output
          sendInitialPrompt();
        }
        const msg = parseNdjsonLine(line);
        if (msg) {
          // Iterate 10: capture the real Claude session_id from the
          // first system/init event. Needed for mid-task mode switching
          // via `--resume <id>` — our own --session-id UUID is NOT
          // resumable (ADR-009).
          if (
            !claudeProcess.claudeSessionId &&
            msg.type === "system" &&
            (msg as { subtype?: string }).subtype === "init"
          ) {
            const sid = (msg as { session_id?: unknown }).session_id;
            if (typeof sid === "string" && sid.length > 0) {
              claudeProcess.claudeSessionId = sid;
            }
          }
          this.onEvent(options.taskId, msg);
        }
      });
    }

    if (child.stderr) {
      this.readLines(child.stderr, (line) => {
        console.error(
          JSON.stringify({
            level: "error",
            source: "claude-cli",
            taskId: options.taskId,
            message: line,
          })
        );
      });
    }

    // Also send initial prompt on stdin "drain" / after small delay as fallback
    // in case the CLI waits for input before producing any output.
    setTimeout(sendInitialPrompt, 2000);

    child.on("error", (err) => {
      console.error(JSON.stringify({
        level: "error",
        source: "claude-cli",
        taskId: options.taskId,
        message: `Spawn error: ${err.message}`,
      }));
      claudeProcess.state = "exited";
      claudeProcess.exitCode = 1;
    });

    child.on("close", (code) => {
      claudeProcess.state = "exited";
      claudeProcess.exitCode = code ?? undefined;
      if (this.onExit) {
        try {
          this.onExit(options.taskId, options.projectId, code);
        } catch (err) {
          console.error(JSON.stringify({
            level: "error",
            message: "onExit handler failed",
            error: String(err),
          }));
        }
      }
    });

    return claudeProcess;
  }

  /**
   * Send a user message (text or multimodal) as NDJSON on stdin.
   * Works as initial prompt AND as follow-up — same pipe, same process.
   */
  sendUserMessage(
    process: ClaudeProcess,
    content: string | UserContentBlock[]
  ): void {
    if (process.state === "exited") {
      throw new AppError("Claude process has exited", 400);
    }
    const stdin = process.process.stdin;
    if (!stdin || stdin.destroyed) {
      throw new AppError("Claude process stdin not available", 500);
    }

    const message = {
      type: "user",
      message: {
        role: "user",
        content: typeof content === "string" ? content : content,
      },
      parent_tool_use_id: null,
      session_id: process.sessionId,
    };

    const line = JSON.stringify(message) + "\n";
    stdin.write(line, (err) => {
      if (err) {
        console.error(JSON.stringify({
          level: "error",
          source: "claude-adapter",
          taskId: process.taskId,
          message: `stdin write error: ${err.message}`,
        }));
      }
    });
  }

  /** Legacy name kept for existing callers — forwards to sendUserMessage. */
  sendStdin(process: ClaudeProcess, input: string): void {
    this.sendUserMessage(process, input);
  }

  terminate(process: ClaudeProcess): void {
    try {
      process.process.stdin?.end();
    } catch {
      // ignore
    }
    process.process.kill("SIGTERM");
    process.state = "exited";
  }

  private readLines(stream: Readable, onLine: (line: string) => void): void {
    let buffer = "";
    stream.on("data", (chunk: Buffer) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) onLine(line);
      }
    });
    stream.on("end", () => {
      if (buffer.trim()) onLine(buffer);
    });
  }
}
