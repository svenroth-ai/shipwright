/*
 * Seed Inbox fixtures — creates 2 projects + 4 tasks with JSONL events
 * that exercise the AskUserQuestion bubble rendering in both Inbox and
 * TaskDetail. Safe to re-run: writes JSONL to a per-run tmp dir so it
 * doesn't stomp real sessions under ~/.claude/projects.
 *
 * Run: cd webui && npx tsx scripts/seed-inbox-fixtures.ts
 */
import { mkdirSync, writeFileSync, appendFileSync } from "node:fs";
import path from "node:path";
import os from "node:os";

const BASE = "http://localhost:3847";
const PROJECTS_DIR = path.join(os.homedir(), ".claude", "projects");
const RUN_ID = Date.now();

async function jpost(url: string, body: unknown) {
  const r = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${url} → ${r.status}: ${await r.text()}`);
  return (await r.json()) as Record<string, any>;
}

function nowIso(offsetSeconds = 0) {
  return new Date(Date.now() + offsetSeconds * 1000).toISOString();
}

function userMsg(sessionId: string, text: string, tsOffset = 0) {
  return JSON.stringify({
    type: "user",
    sessionId,
    timestamp: nowIso(tsOffset),
    message: { role: "user", content: text },
  });
}

function assistantText(sessionId: string, text: string, tsOffset = 0) {
  return JSON.stringify({
    type: "assistant",
    sessionId,
    timestamp: nowIso(tsOffset),
    message: {
      role: "assistant",
      content: [{ type: "text", text }],
    },
  });
}

interface AskOption {
  label: string;
  description?: string;
}

function assistantAsk(
  sessionId: string,
  toolUseId: string,
  question: string,
  options: AskOption[] = [],
  header?: string,
  tsOffset = 0,
  multiSelect = false,
) {
  return JSON.stringify({
    type: "assistant",
    sessionId,
    timestamp: nowIso(tsOffset),
    message: {
      role: "assistant",
      content: [
        {
          type: "tool_use",
          id: toolUseId,
          name: "AskUserQuestion",
          input: {
            questions: [
              { question, header, options, multiSelect },
            ],
          },
        },
      ],
    },
  });
}

function userToolResult(sessionId: string, toolUseId: string, answer: string, tsOffset = 0) {
  return JSON.stringify({
    type: "user",
    sessionId,
    timestamp: nowIso(tsOffset),
    message: {
      role: "user",
      content: [
        { type: "tool_result", tool_use_id: toolUseId, content: answer },
      ],
    },
  });
}

async function createProject(name: string) {
  const tmpPath = path.join(os.tmpdir(), `shipwright-seed-${RUN_ID}-${name.replace(/\W+/g, "-")}`);
  mkdirSync(tmpPath, { recursive: true });
  const res = await jpost("/api/projects", { name, path: tmpPath });
  return res.data as { id: string; name: string; path: string };
}

async function createTask(title: string, projectId: string, cwd: string) {
  const res = await jpost("/api/external/tasks", { title, cwd, projectId });
  return res.task as { taskId: string; sessionUuid: string };
}

function writeJsonl(task: { sessionUuid: string }, lines: string[]) {
  const encodedDir = path.join(PROJECTS_DIR, `seed-${RUN_ID}-${task.sessionUuid.slice(0, 8)}`);
  mkdirSync(encodedDir, { recursive: true });
  const jsonl = path.join(encodedDir, `${task.sessionUuid}.jsonl`);
  writeFileSync(jsonl, lines.join("\n") + "\n", "utf-8");
  return jsonl;
}

async function main() {
  console.log(`Seeding Inbox fixtures (run ${RUN_ID})...`);

  const webshop = await createProject(`Webshop (seed ${RUN_ID})`);
  const gateway = await createProject(`API Gateway (seed ${RUN_ID})`);
  console.log(`  ✓ project ${webshop.name} (${webshop.id})`);
  console.log(`  ✓ project ${gateway.name} (${gateway.id})`);

  // ── Task 1: Webshop / Deploy pipeline — single pending ask
  {
    const t = await createTask("Deploy pipeline to prod", webshop.id, webshop.path);
    const tu = `tu-${RUN_ID}-1`;
    writeJsonl(t, [
      userMsg(t.sessionUuid, "Deploy the current main branch to production.", -300),
      assistantText(t.sessionUuid, "Running pre-flight checks… smoke tests green. One gate remains.", -290),
      assistantAsk(
        t.sessionUuid,
        tu,
        "Previous deploy is still live at v1.2.3. How should I proceed?",
        [
          { label: "Rollback to v1.2.3", description: "Revert and investigate" },
          { label: "Retry deploy", description: "Re-run the pipeline" },
          { label: "Abort", description: "Leave current prod untouched" },
        ],
        "Deploy strategy",
        -280,
      ),
    ]);
    console.log(`  ✓ task "${t.sessionUuid.slice(0, 8)}" — 1 pending ask`);
  }

  // ── Task 2: Webshop / Refactor auth — TWO pending asks
  {
    const t = await createTask("Refactor auth middleware", webshop.id, webshop.path);
    const tu1 = `tu-${RUN_ID}-2a`;
    const tu2 = `tu-${RUN_ID}-2b`;
    writeJsonl(t, [
      userMsg(t.sessionUuid, "Clean up the legacy session-token handling in auth.ts.", -600),
      assistantText(t.sessionUuid, "Reviewed auth.ts. Two decisions needed before I refactor.", -595),
      assistantAsk(
        t.sessionUuid,
        tu1,
        "Keep cookie-based sessions or switch to JWT?",
        [
          { label: "Keep cookies", description: "Lower migration risk" },
          { label: "Switch to JWT", description: "Stateless, aligns with mobile roadmap" },
        ],
        "Session strategy",
        -590,
      ),
      assistantAsk(
        t.sessionUuid,
        tu2,
        "What token TTL?",
        [
          { label: "15 minutes" },
          { label: "1 hour" },
          { label: "24 hours" },
        ],
        "Token lifetime",
        -585,
      ),
    ]);
    console.log(`  ✓ task "${t.sessionUuid.slice(0, 8)}" — 2 pending asks`);
  }

  // ── Task 3: API Gateway / Fix flaky test — single pending ask after real chat
  {
    const t = await createTask("Fix flaky retry test", gateway.id, gateway.path);
    const tu = `tu-${RUN_ID}-3`;
    writeJsonl(t, [
      userMsg(t.sessionUuid, "gateway.retry.spec.ts fails ~10% of runs on CI. Investigate.", -900),
      assistantText(
        t.sessionUuid,
        "Inspected the spec. The flake is the retry-count assertion — test waits 100 ms but CI occasionally takes 140 ms.",
        -895,
      ),
      assistantText(
        t.sessionUuid,
        "Two fixes: increase wait, or inject a deterministic clock. Both are safe; injection is cleaner long-term.",
        -890,
      ),
      assistantAsk(
        t.sessionUuid,
        tu,
        "Which fix do you want?",
        [
          { label: "Inject deterministic clock", description: "Cleaner, small refactor" },
          { label: "Bump wait to 250ms", description: "One-liner" },
          { label: "Both", description: "Belt-and-braces" },
        ],
        "Flake fix",
        -885,
      ),
    ]);
    console.log(`  ✓ task "${t.sessionUuid.slice(0, 8)}" — 1 pending ask + chat context`);
  }

  // ── Task 4: API Gateway / OAuth scope — ask ALREADY answered (NOT in Inbox, shows in TaskDetail)
  {
    const t = await createTask("Add OAuth scope for read:webhooks", gateway.id, gateway.path);
    const tu = `tu-${RUN_ID}-4`;
    writeJsonl(t, [
      userMsg(t.sessionUuid, "Add a read:webhooks scope to the OAuth consent screen.", -1800),
      assistantText(t.sessionUuid, "Found the consent config in oauth/scopes.ts. Adding read:webhooks.", -1790),
      assistantAsk(
        t.sessionUuid,
        tu,
        "Should the new scope be granted by default to existing apps?",
        [
          { label: "Yes — add to default bundle" },
          { label: "No — opt-in only" },
        ],
        "Default grant",
        -1780,
      ),
      userToolResult(t.sessionUuid, tu, "No — opt-in only", -1700),
      assistantText(
        t.sessionUuid,
        "Understood. Added read:webhooks as opt-in. Committed as `feat(oauth): add read:webhooks scope`.",
        -1690,
      ),
    ]);
    console.log(`  ✓ task "${t.sessionUuid.slice(0, 8)}" — resolved (not in Inbox, but full chat in TaskDetail)`);
  }

  console.log("\nDone. Open http://localhost:5173/inbox to verify.");
  console.log("Expected: 2 project group headers, 4 pending items total (1+2+1+0).");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
