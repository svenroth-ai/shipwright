import path from "path";
import os from "os";

export interface ServerConfig {
  port: number;
  maxConcurrent: number;
  registryDir: string;
  heartbeatIntervalMs: number;
  staticDir: string;
}

export function getConfig(): ServerConfig {
  return {
    port: parseInt(process.env.PORT ?? "3847", 10),
    maxConcurrent: parseInt(
      process.env.SHIPWRIGHT_MAX_CONCURRENT ?? "3",
      10
    ),
    registryDir: path.join(os.homedir(), ".shipwright-webui"),
    heartbeatIntervalMs: 30_000,
    staticDir: path.resolve(__dirname, "../../client/dist"),
  };
}
