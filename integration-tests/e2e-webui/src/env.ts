// Operator inputs. Four variables, NO defaults: the spec refuses to start without the first three.
// Each is read from the process environment first, then from an env file outside the repo.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const REQUIRED = [
  "SHIPWRIGHT_E2E_PERMISSION_MODE",
  "SHIPWRIGHT_E2E_WEBUI_DIR",
  "SHIPWRIGHT_E2E_MAX_MINUTES",
] as const;
export const OPTIONAL = ["SHIPWRIGHT_E2E_WORKDIR", "SHIPWRIGHT_E2E_RESUME_RUN"] as const;

export type Source = "process-env" | "env-file" | "unset";

export interface E2EConfig {
  permissionMode: string;
  webuiDir: string;
  maxMinutes: number;
  workdir: string;
  /** Optional run folder (run-<id> under the workdir) of an earlier, stopped run to continue; null = a new run. */
  resumeRun: string | null;
  /** Which source supplied each variable (never a value that could be a secret). */
  sources: Record<string, Source>;
  envFile: string;
  envFileFound: boolean;
}

/** KEY=VALUE lines, `#` comments, optional single/double quotes. Later lines win. */
export function parseEnvFile(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (value.length >= 2 && /^(["']).*\1$/.test(value)) value = value.slice(1, -1);
    out[key] = value;
  }
  return out;
}

/** Default env file: ../autorune2e/.env relative to the repo root (no user path is hard-coded). */
export function defaultEnvFile(repoRoot: string): string {
  return path.resolve(repoRoot, "..", "autorune2e", ".env");
}

export class ConfigError extends Error {}

export function loadConfig(
  repoRoot: string,
  env: NodeJS.ProcessEnv = process.env,
  readFile: (p: string) => string | null = (p) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8") : null),
): E2EConfig {
  const envFile = env.SHIPWRIGHT_E2E_ENV_FILE
    ? path.resolve(env.SHIPWRIGHT_E2E_ENV_FILE)
    : defaultEnvFile(repoRoot);
  const fileText = readFile(envFile);
  const fromFile = fileText === null ? {} : parseEnvFile(fileText);

  const sources: Record<string, Source> = {};
  const values: Record<string, string> = {};
  for (const name of [...REQUIRED, ...OPTIONAL]) {
    const fromEnv = env[name];
    if (fromEnv !== undefined && fromEnv.trim() !== "") {
      values[name] = fromEnv.trim();
      sources[name] = "process-env";
    } else if (fromFile[name] !== undefined && fromFile[name].trim() !== "") {
      values[name] = fromFile[name].trim();
      sources[name] = "env-file";
    } else {
      sources[name] = "unset";
    }
  }

  const missing = REQUIRED.filter((n) => sources[n] === "unset");
  if (missing.length > 0) {
    throw new ConfigError(
      `Refusing to start: ${missing.join(", ")} not set (no defaults). Set them in the environment or in ` +
        `${envFile} (see integration-tests/e2e-webui/README.md).`,
    );
  }

  const mode = values.SHIPWRIGHT_E2E_PERMISSION_MODE;
  if (!/^[A-Za-z]+$/.test(mode)) {
    throw new ConfigError("Refusing to start: SHIPWRIGHT_E2E_PERMISSION_MODE must be a single word such as acceptEdits.");
  }
  const minutes = Number(values.SHIPWRIGHT_E2E_MAX_MINUTES);
  if (!Number.isInteger(minutes) || minutes < 1) {
    throw new ConfigError("Refusing to start: SHIPWRIGHT_E2E_MAX_MINUTES must be a whole number of minutes, 1 or more.");
  }
  const webuiDir = path.resolve(values.SHIPWRIGHT_E2E_WEBUI_DIR);
  const workdir = values.SHIPWRIGHT_E2E_WORKDIR ? path.resolve(values.SHIPWRIGHT_E2E_WORKDIR) : path.join(os.tmpdir(), "shipwright-e2e");

  return {
    permissionMode: mode,
    webuiDir,
    maxMinutes: minutes,
    workdir,
    resumeRun: values.SHIPWRIGHT_E2E_RESUME_RUN ? path.resolve(values.SHIPWRIGHT_E2E_RESUME_RUN) : null,
    sources,
    envFile,
    envFileFound: fileText !== null,
  };
}
