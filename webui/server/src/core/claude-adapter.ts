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
 * Claude CLI permission modes.
 *
 * Iterate 14.9 — `auto` added. In Auto mode the CLI picks the best
 * permission mode per turn (mirrors the VS Code extension's Auto mode
 * toggle). We pass it straight through as `--permission-mode auto`.
 */
export type PermissionMode = "auto" | "default" | "acceptEdits" | "plan" | "bypassPermissions";

/** Claude CLI accepts these short aliases directly via --model.
 *  Kept narrow so we don't silently pass arbitrary strings into the CLI. */
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
   * Claude CLI model alias — opus / sonnet / haiku. When set, pushes
   * `--model <alias>` into the spawn args. When undefined, the CLI picks
   * its compiled-in default (currently claude-opus-4-5). Iterate 9 wired
   * this up after finding the UI toolbar selection was a placebo.
   */
  model?: ModelAlias;
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
    const mode: PermissionMode = options.permissionMode ?? "bypassPermissions";
    if (mode === "bypassPermissions") {
      args.push("--dangerously-skip-permissions");
    } else {
      args.push("--permission-mode", mode);
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

    console.log(JSON.stringify({
      level: "info",
      source: "claude-adapter",
      taskId: options.taskId,
      command,
      argsCount: fullArgs.length,
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
