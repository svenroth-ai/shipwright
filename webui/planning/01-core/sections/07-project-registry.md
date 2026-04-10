# Section 07: Multi-Project Registry & File Watcher

## Goal

Implement the project registry that persists to `~/.shipwright-webui/projects.json` with full CRUD operations, project discovery by scanning directories for Shipwright config files, a config reader that parses `shipwright_*_config.json` files and derives pipeline state, and a chokidar-based file watcher that monitors event and config files per project with debounced SSE notifications.

## FRs Covered

- **FR-01.24** — Project registry persistence with CRUD operations
- **FR-01.25** — Per-project metadata (name, path, profile, status, lastActive)
- **FR-01.26** — Project discovery by scanning for config files
- **FR-01.33** — Config reader for shipwright_*_config.json files
- **FR-01.34** — File watcher on events and config files per project
- **FR-01.35** — Debounced file watcher events

## Files to Create/Modify

| Action | Path |
|--------|------|
| Create | `server/src/core/project-manager.ts` |
| Create | `server/src/bridge/config-reader.ts` |
| Create | `server/src/core/file-watcher.ts` |
| Create | `server/src/core/project-manager.test.ts` |
| Create | `server/src/bridge/config-reader.test.ts` |
| Create | `server/src/core/file-watcher.test.ts` |

## Implementation Steps

### Step 1: Define ProjectManagerDeps Interface

Create `server/src/core/project-manager.ts`. Export an injectable dependency interface:

```typescript
export interface ProjectManagerDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  readdirSync: (path: string, opts?: { withFileTypes: boolean }) => fs.Dirent[];
}
```

### Step 2: Implement ProjectManager Class

Export `class ProjectManager`:

- **Constructor** takes `registryPath: string` (default `~/.shipwright-webui/projects.json`) and `ProjectManagerDeps`.
- **Private state:** `projects: Map<string, Project>` as in-memory cache.

### Step 3: Implement `load()` Method

```typescript
async load(): Promise<void>
```

- Read registry file, parse JSON array, populate the `projects` Map keyed by `id`.
- If file does not exist: create the directory (`~/.shipwright-webui/`) with `mkdirSync({ recursive: true })`, initialize empty registry, write `[]` to the file.

### Step 4: Implement `create()` Method

```typescript
create(data: Omit<Project, "id" | "createdAt" | "lastActive">): Project
```

- Validate that `data.path` exists on disk via `deps.existsSync()`. Throw `AppError(400)` if not.
- Generate UUID for `id`.
- Set `createdAt` and `lastActive` to `new Date().toISOString()`.
- Add to Map, call `persist()`.
- Return the created `Project`.

### Step 5: Implement Remaining CRUD Methods

- `getAll(): Project[]` — return all projects from Map, sorted by `lastActive` descending.
- `getById(id: string): Project | undefined` — lookup in Map.
- `update(id: string, patch: Partial<Project>): Project` — find by id, throw `AppError(404)` if missing. Merge patch, update `lastActive`. Persist and return.
- `delete(id: string): void` — remove from Map, persist. Throw `AppError(404)` if not found.
- `touchLastActive(id: string): void` — update `lastActive` to now, persist.

### Step 6: Implement `discover()` Method

```typescript
discover(directory: string): Project[]
```

- Scan `directory` for subdirectories using `deps.readdirSync()` with `withFileTypes: true`.
- For each subdirectory: check if it contains `shipwright_run_config.json` OR `shipwright_project_config.json` via `deps.existsSync()`.
- For each found: create a `Project` object with name derived from directory basename, path from full path, profile `"default"`, status `"active"`.
- Return the array of newly discovered projects (not yet persisted -- caller decides whether to add them).

### Step 7: Implement `persist()` Method

```typescript
private async persist(): Promise<void>
```

- Serialize all projects from Map as a JSON array, write to `registryPath`.

### Step 8: Create Config Reader

Create `server/src/bridge/config-reader.ts`. Export:

- `readConfigFile<T>(filePath: string, deps?: FileSystemDeps): Promise<T | null>` — read and parse JSON. Return `null` if file does not exist (no throw).
- `readAllConfigs(projectDir: string, deps?: FileSystemDeps): Promise<Record<string, unknown>>` — read all 7 known config files: `shipwright_run_config.json`, `shipwright_project_config.json`, `shipwright_plan_config.json`, `shipwright_build_config.json`, `shipwright_test_config.json`, `shipwright_deploy_config.json`, `shipwright_changelog_config.json`. Return a map of config name to parsed content, omitting entries where the file is missing.
- `derivePipelineFromConfigs(configs: Record<string, unknown>): PipelinePhase[]` — for each of the 7 phases (project, design, plan, build, test, changelog, deploy), check if a corresponding config exists. If config exists and has completion markers -> `completed`. If config exists but no completion -> `running` or `pending` based on phase order. If no config -> `pending`. This provides pipeline state even without events (standalone projects).

### Step 9: Create FileWatcher

Create `server/src/core/file-watcher.ts`. Export:

```typescript
export interface FileWatcherDeps {
  watch: typeof chokidar.watch;
}
```

Export `class FileWatcher`:

- **Private state:** `watchers: Map<string, FSWatcher>` keyed by projectId, `debounceTimers: Map<string, NodeJS.Timeout>`.
- `watchProject(projectId: string, projectDir: string, onChange: (type: string, path: string) => void): void`:
  - Watch `${projectDir}/shipwright_events.jsonl` and `${projectDir}/shipwright_*_config.json` using chokidar.
  - On any change event: determine type (`"event"` for events file, `"config"` for config files). Clear existing debounce timer for this project. Set a new 300ms timer. When timer fires, call `onChange(type, changedPath)`.
- `unwatchProject(projectId: string): void` — close the watcher, clear debounce timer, remove from Map.
- `unwatchAll(): void` — iterate all watchers, close each, clear all timers.

### Step 10: Write Unit Tests for ProjectManager

Create `server/src/core/project-manager.test.ts`:

1. `create()` assigns UUID, sets timestamps, calls persist.
2. `getAll()` returns projects sorted by `lastActive` descending.
3. `update()` merges patch and updates `lastActive`.
4. `delete()` removes project from Map and persists.
5. `load()` with non-existent file creates empty registry and directory.
6. `load()` with existing file populates in-memory Map correctly.
7. `discover()` finds directories containing Shipwright config files.
8. `discover()` ignores directories without config files.
9. `getById()` returns undefined for non-existent project.
10. `create()` with non-existent path throws 400 error.

### Step 11: Write Unit Tests for Config Reader

Create `server/src/bridge/config-reader.test.ts`:

1. Valid config file -> parsed JSON returned.
2. Missing config file -> null returned (no throw).
3. `readAllConfigs` reads all 7 config types, omits missing ones.
4. `derivePipelineFromConfigs` with run_config + build_config -> correct phase statuses.
5. Pipeline derivation without run_config (standalone) -> still produces valid phases array.

### Step 12: Write Unit Tests for FileWatcher

Create `server/src/core/file-watcher.test.ts`:

1. Mock chokidar: emit `change` on events file -> `onChange` called with `"event"`.
2. Mock chokidar: emit `change` on config file -> `onChange` called with `"config"`.
3. Two rapid changes within 300ms -> `onChange` called only once (debounce verified).
4. `unwatchProject` closes the watcher and clears timer.
5. `unwatchAll` closes all watchers.

## Test Strategy

### Unit Tests

| File | Coverage |
|------|----------|
| `server/src/core/project-manager.test.ts` | CRUD operations, registry persistence, discovery, validation |
| `server/src/bridge/config-reader.test.ts` | Config parsing, missing file handling, pipeline derivation |
| `server/src/core/file-watcher.test.ts` | Watch setup, debounce behavior, cleanup |

### Integration Tests

No HTTP routes in this section. Integration testing of project routes happens in Section 10.

### Mocking Strategy

- `ProjectManagerDeps` — mock all FS operations to use in-memory storage.
- `FileSystemDeps` (config-reader) — mock `readFile` and `existsSync`.
- `FileWatcherDeps` — mock `chokidar.watch` to return a fake `FSWatcher` that can emit events programmatically.

## Dependencies

- **Section 02 (Shared Types)** — `Project`, `ProjectStatus`, `PipelinePhase`, `PhaseStatus` interfaces.
- **Section 03 (Event System)** — `EventStore` for event replay when a new project is registered.
- **Section 01 (Project Setup)** — `config.ts` for `registryDir` path, `AppError` class from error handler.
- **npm packages:** `chokidar`, `uuid`.

## Acceptance Criteria

**FR-01.24: Project Registry**
- [ ] Projects are persisted to ~/.shipwright-webui/projects.json
- [ ] Create, read, update, and delete operations work correctly
- [ ] Registry file is created automatically if it does not exist

**FR-01.25: Project Metadata**
- [ ] Each project entry stores name, path, profile, status, and lastActive
- [ ] lastActive is updated on any project interaction

**FR-01.26: Project Discovery (Should)**
- [ ] Scanning a directory finds subdirectories with shipwright_run_config.json
- [ ] Scanning also finds standalone projects with shipwright_project_config.json (no orchestrator)
- [ ] Directories without config files are ignored

**FR-01.33: Config Reader**
- [ ] shipwright_run_config.json is read and parsed
- [ ] shipwright_plan_config.json, shipwright_build_config.json etc. are read when present
- [ ] Missing config files are handled gracefully (not an error)
- [ ] Pipeline state is derivable from events + phase configs alone when shipwright_run_config.json is missing (standalone invocation)

**FR-01.34: File Watcher**
- [ ] Changes to shipwright_events.jsonl trigger SSE updates
- [ ] Changes to shipwright_*_config.json trigger SSE updates
- [ ] File watchers are created per registered project

**FR-01.35: Debounced File Watcher (Should)**
- [ ] Rapid file changes within 300ms are debounced into a single callback
- [ ] SSE clients are not flooded during rapid file changes
