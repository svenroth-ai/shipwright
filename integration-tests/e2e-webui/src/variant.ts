// The checks that differ between the two fixtures, behind one interface so the spec does not branch on the fixture name:
// the API checks, the self-containment check (S05), and the board checks (S01, S02, S04) in the browser.
import type { Page } from "@playwright/test";
import { runApiChecks, type Call, type ThreadState } from "./board-api.js";
import { runRealApiChecks } from "./board-api-real.js";
import { checkBoardShape, checkBoardTokens, snapshotBoard } from "./board-dom.js";
import { checkMasterDetailShape, snapshotMasterDetail } from "./board-dom-real.js";
import type { Checklist } from "./checklist.js";
import { REAL_FIXTURE_NAME, type FixtureName } from "./fixture.js";
import { checkSelfContainedWithAdapter } from "./project-checks-adapter.js";
import { checkSelfContained } from "./project-checks.js";
import { parseFontTokens, parseTokens } from "./tokens.js";

export interface Variant {
  api: (call: Call, checklist: Checklist) => Promise<{ state: ThreadState }>;
  selfContained: (projectPath: string, checklist: Checklist) => void;
  /** Takes the visual-guidelines text; records S01, S02, S04 from the served board at `app`. */
  board: (app: Page, guidelines: string, state: ThreadState, checklist: Checklist) => Promise<void>;
}

const tabsVariant: Variant = {
  api: runApiChecks,
  selfContained: checkSelfContained,
  async board(app, guidelines, state, checklist) {
    const declared = parseTokens(guidelines);
    const snap = await snapshotBoard(app, Object.keys(declared));
    checkBoardShape(snap, checklist, state.perPlatform);
    checkBoardTokens(snap, declared, checklist);
  },
};

const masterDetailVariant: Variant = {
  api: runRealApiChecks,
  selfContained: checkSelfContainedWithAdapter,
  async board(app, guidelines, state, checklist) {
    const declared = parseTokens(guidelines);
    const fonts = parseFontTokens(guidelines);
    const snap = await snapshotMasterDetail(app, [...Object.keys(declared), ...Object.keys(fonts)], state as Parameters<typeof snapshotMasterDetail>[2]);
    checkMasterDetailShape(snap, checklist, state.perPlatform);
    checkBoardTokens(snap, declared, checklist, fonts);
  },
};

export const variantFor = (fixture: FixtureName): Variant => (fixture === REAL_FIXTURE_NAME ? masterDetailVariant : tabsVariant);
