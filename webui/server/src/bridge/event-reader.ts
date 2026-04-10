import type { ShipwrightEvent } from "../../../client/src/types/event.js";

export interface FileSystemDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  existsSync: (path: string) => boolean;
}

export async function readEventsFromFile(
  filePath: string,
  fs: FileSystemDeps
): Promise<ShipwrightEvent[]> {
  if (!fs.existsSync(filePath)) {
    return [];
  }

  let content: string;
  try {
    content = await fs.readFile(filePath, "utf-8");
  } catch {
    return [];
  }

  const lines = content.split("\n");
  const events: ShipwrightEvent[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    try {
      const parsed = JSON.parse(line);
      if (typeof parsed.type !== "string" || typeof parsed.timestamp !== "string") {
        console.warn(JSON.stringify({ level: "warn", message: `Skipping line ${i + 1}: missing type or timestamp` }));
        continue;
      }
      events.push(parsed as ShipwrightEvent);
    } catch {
      console.warn(JSON.stringify({ level: "warn", message: `Skipping corrupt line ${i + 1}` }));
    }
  }

  return events;
}
