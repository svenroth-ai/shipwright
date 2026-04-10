import fs from "fs";
import path from "path";
import { readFile } from "fs/promises";
import { AppError } from "../middleware/error-handler.js";

export interface FileTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  children?: FileTreeNode[];
}

const EXCLUDED = new Set([
  "node_modules",
  ".git",
  "__pycache__",
  ".venv",
  ".shipwright-webui",
  "dist",
  ".next",
]);

export function buildFileTree(
  projectDir: string,
  relativePath: string = ""
): FileTreeNode[] {
  const fullPath = path.join(projectDir, relativePath);
  if (!fs.existsSync(fullPath)) return [];

  const entries = fs.readdirSync(fullPath, { withFileTypes: true });
  const nodes: FileTreeNode[] = [];

  for (const entry of entries) {
    if (EXCLUDED.has(entry.name)) continue;
    if (entry.name.startsWith(".")) continue;

    const entryRelPath = relativePath ? `${relativePath}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      nodes.push({
        name: entry.name,
        path: entryRelPath,
        type: "directory",
        children: buildFileTree(projectDir, entryRelPath),
      });
    } else {
      nodes.push({
        name: entry.name,
        path: entryRelPath,
        type: "file",
      });
    }
  }

  return nodes.sort((a, b) => {
    if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export async function readFileContent(
  filePath: string,
  projectDir: string
): Promise<string> {
  const resolved = path.resolve(projectDir, filePath);
  if (!resolved.startsWith(path.resolve(projectDir))) {
    throw new AppError("Path traversal not allowed", 400);
  }
  return readFile(resolved, "utf-8");
}
