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

export interface ClaudeSpawnOptions {
  projectDir: string;
  projectId: string;
  taskId: string;
  sessionId?: string;
  /**
   * Session behavior:
   * - false: new session with --session-id
   * - true: resume last session in cwd with --continue
   * - "explicit": resume specific session with --resume <sessionId>
   */
  resume: boolean | "explicit";
  pluginDirs: string[];
  prompt: string;
  claudeCliPath?: string;
}

/**
 * Resolve the Claude CLI command for the current platform.
 * On Windows, .cmd shims don't pipe stdout correctly through shell: true,
 * so we resolve the actual cli.js and run it directly with node.
 */
function resolveClaudeCommand(cliPath?: string): { command: string; prefixArgs: string[] } {
  if (cliPath) return { command: cliPath, prefixArgs: [] };

  if (process.platform === "win32") {
    // Resolve the npm global cli.js directly to avoid cmd.exe stdout buffering issues
    const npmGlobal = process.env.APPDATA
      ? path.join(process.env.APPDATA, "npm", "node_modules", "@anthropic-ai", "claude-code", "cli.js")
      : null;
    if (npmGlobal && fs.existsSync(npmGlobal)) {
      return { command: process.execPath, prefixArgs: [npmGlobal] };
    }
  }

  return { command: "claude", prefixArgs: [] };
}

export class ClaudeAdapter {
  constructor(
    private deps: SpawnDeps,
    private onEvent: (taskId: string, msg: NdjsonMessage) => void,
    private onExit?: (taskId: string, projectId: string, exitCode: number | null) => void
  ) {}

  spawn(options: ClaudeSpawnOptions): ClaudeProcess {
    const args: string[] = [
      "--output-format", "stream-json",
      "--verbose",
      "--dangerously-skip-permissions",
    ];

    for (const dir of options.pluginDirs) {
      args.push("--plugin-dir", dir);
    }

    if (options.resume === "explicit" && options.sessionId) {
      args.push("--resume", options.sessionId);
    } else if (options.resume === true) {
      args.push("--continue");
    } else if (options.sessionId) {
      args.push("--session-id", options.sessionId);
    }

    args.push("-p", options.prompt);

    const { command, prefixArgs } = resolveClaudeCommand(options.claudeCliPath);
    const fullArgs = [...prefixArgs, ...args];

    console.log(JSON.stringify({ level: "info", source: "claude-adapter", taskId: options.taskId, command, argsCount: fullArgs.length, resume: options.resume }));

    // In print mode (-p) Claude CLI exits after the response, so stdin should
    // be ignored regardless of resume flag. Interactive follow-ups are handled
    // by re-spawning with --resume <sessionId> + the new user message as prompt.
    const stdinMode = "ignore";
    const child = this.deps.spawn(command, fullArgs, {
      cwd: options.projectDir,
      stdio: [stdinMode as "pipe", "pipe", "pipe"],
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

    if (child.stdout) {
      this.readLines(child.stdout, (line) => {
        if (claudeProcess.state === "spawning") {
          claudeProcess.state = "running";
        }
        const msg = parseNdjsonLine(line);
        if (msg) {
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

    child.on("error", (err) => {
      console.error(
        JSON.stringify({
          level: "error",
          source: "claude-cli",
          taskId: options.taskId,
          message: `Spawn error: ${err.message}`,
        })
      );
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
          console.error(JSON.stringify({ level: "error", message: "onExit handler failed", error: String(err) }));
        }
      }
    });

    return claudeProcess;
  }

  sendStdin(process: ClaudeProcess, input: string): void {
    if (process.state === "exited") {
      throw new AppError("Process has exited", 400);
    }
    process.process.stdin?.write(input + "\n");
  }

  terminate(process: ClaudeProcess): void {
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
