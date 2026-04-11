import type { ChildProcess } from "child_process";
import type { Readable } from "stream";
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
  process: ChildProcess;
}

export interface SpawnDeps {
  spawn: (
    command: string,
    args: string[],
    options: { cwd: string; stdio: [string, string, string] }
  ) => ChildProcess;
}

export interface ClaudeSpawnOptions {
  projectDir: string;
  projectId: string;
  taskId: string;
  sessionId?: string;
  resume: boolean;
  pluginDirs: string[];
  prompt: string;
  claudeCliPath?: string;
}

export class ClaudeAdapter {
  constructor(
    private deps: SpawnDeps,
    private onEvent: (taskId: string, msg: NdjsonMessage) => void
  ) {}

  spawn(options: ClaudeSpawnOptions): ClaudeProcess {
    const args: string[] = ["--output-format", "stream-json"];

    for (const dir of options.pluginDirs) {
      args.push("--plugin-dir", dir);
    }

    if (options.resume) {
      args.push("--continue");
    } else if (options.sessionId) {
      args.push("--session-id", options.sessionId);
    }

    args.push("-p", options.prompt);

    const command = options.claudeCliPath ?? "claude";
    const child = this.deps.spawn(command, args, {
      cwd: options.projectDir,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const claudeProcess: ClaudeProcess = {
      pid: child.pid ?? 0,
      taskId: options.taskId,
      projectId: options.projectId,
      sessionId: options.sessionId ?? options.taskId,
      state: "spawning",
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
