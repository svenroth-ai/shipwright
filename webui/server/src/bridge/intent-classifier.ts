import { spawn } from "child_process";

export interface ClassifyResult {
  intent: string;
  affected_frs?: string[];
}

export interface ComplexityResult {
  complexity: string;
}

function runScript(
  command: string,
  args: string[],
  cwd: string,
  timeout: number = 10000
): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn(command, args, { cwd, stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";

    const timer = setTimeout(() => {
      proc.kill();
      reject(new Error("Timeout"));
    }, timeout);

    proc.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
    proc.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
    proc.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve(stdout);
      else reject(new Error(`Exit ${code}: ${stderr}`));
    });
    proc.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

export async function classifyIntent(
  description: string,
  projectDir: string
): Promise<ClassifyResult> {
  try {
    const output = await runScript(
      "uv",
      ["run", "classify_intent.py", description],
      projectDir
    );
    return JSON.parse(output.trim());
  } catch {
    return { intent: "unknown" };
  }
}

export async function classifyComplexity(
  description: string,
  projectDir: string
): Promise<ComplexityResult> {
  try {
    const output = await runScript(
      "uv",
      ["run", "classify_complexity.py", description],
      projectDir
    );
    return JSON.parse(output.trim());
  } catch {
    return { complexity: "unknown" };
  }
}
