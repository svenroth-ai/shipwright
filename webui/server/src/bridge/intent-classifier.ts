import { spawn } from "child_process";

export interface ClassifyResult {
  intent: string;
  affected_frs?: string[];
}

export interface ComplexityResult {
  complexity: string;
}

export interface PhaseResult {
  phase: string;
  confidence: number;
}

export const VALID_PHASES = [
  "project",
  "design",
  "plan",
  "build",
  "test",
  "security",
  "deploy",
  "changelog",
  "compliance",
  "iterate",
  "preview",
] as const;

export type Phase = (typeof VALID_PHASES)[number];

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

export async function classifyPhase(
  description: string,
  projectDir: string
): Promise<PhaseResult> {
  try {
    const output = await runScript(
      "uv",
      ["run", "classify_phase.py", description],
      projectDir
    );
    const parsed = JSON.parse(output.trim()) as { phase?: string; confidence?: number };
    const phase =
      typeof parsed.phase === "string" && (VALID_PHASES as readonly string[]).includes(parsed.phase)
        ? parsed.phase
        : "project";
    const confidence =
      typeof parsed.confidence === "number" && Number.isFinite(parsed.confidence)
        ? parsed.confidence
        : 0;
    return { phase, confidence };
  } catch {
    return { phase: "project", confidence: 0 };
  }
}
