/**
 * Doc-sync meta-test.
 *
 * Iterate 3 shipped 6 new client components + 6 new server modules/configs.
 * `webui/CLAUDE.md` is the single source of truth for the file map and for
 * the load-bearing DO-NOT regression guards. It is easy to ship a new
 * component and forget to list it in CLAUDE.md — this test catches that
 * drift at CI time.
 *
 * Each token below MUST appear at least once in `webui/CLAUDE.md`. When
 * adding new production components/modules in future iterates, extend the
 * list here as part of the same commit.
 *
 * See:
 *   - webui/agent_docs/decision_log.md — ADR-044 (iterate 3 close-out).
 *   - webui/planning/iterate-3/sections/06-doc-sync-and-iterate-close.md — spec.
 */

import { describe, it, expect, beforeAll } from 'vitest';

// Vitest runs this under Node, so `fs` + `path` are available at runtime —
// the client has no `@types/node`, so we minimally type the dynamic imports.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const require: any;

const REQUIRED_TOKENS = [
  // Iterate 3 client components (section 3.3 + 3.4)
  'FolderTree',
  'SmartViewer',
  'NewIssueModal',
  'PreviewButton',
  'CreateMenuSplitButton',
  'TaskDetailThreePane',
  // Iterate 3 server modules + config
  'default-actions.json',
  'project-actions-loader',
  'actions-substitute',
  'preview-session-manager',
  'path-guard',
  'gitignore-cache',
] as const;

let claudeMd = '';

beforeAll(async () => {
  // Dynamic import keeps the TS type-check free of @types/node.
  // Vitest exposes both ESM and CJS interop at runtime.
  const fs = await import('node:fs' as string);
  const path = await import('node:path' as string);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const url = await import('node:url' as string) as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const here = path.dirname(url.fileURLToPath((import.meta as any).url));
  // client/src/test → ../../../CLAUDE.md (= webui/CLAUDE.md)
  const claudeMdPath = path.resolve(here, '../../../CLAUDE.md');
  claudeMd = fs.readFileSync(claudeMdPath, 'utf8');
});

describe('doc-sync: webui/CLAUDE.md file map', () => {
  for (const token of REQUIRED_TOKENS) {
    it(`lists "${token}" in the file map`, () => {
      expect(claudeMd).toContain(token);
    });
  }

  it('has at least one reference to ADR-044 (iterate 3 close-out)', () => {
    expect(claudeMd).toMatch(/ADR-044/);
  });

  it('has the DO-NOT guard #11 about hardcoded shipwright-run strings', () => {
    expect(claudeMd).toMatch(/shipwright-run/);
    expect(claudeMd).toMatch(/\/api\/external\/projects\/:id\/actions/);
  });
});
