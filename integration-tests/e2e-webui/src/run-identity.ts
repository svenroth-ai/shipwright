// What a run is tied to: the plugin code it loads (commit plus a digest of uncommitted changes under plugins/ and
// shared/) and the Brief package as it lies on disk. Both are computed, never read back from a recorded field:
// a recorded hash proves nothing about the files, and a dirty-tree marker says nothing about WHICH changes.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const CODE_DIRS = ["plugins", "shared"];

/**
 * The git trees of plugins/ and shared/ at HEAD ("plugins:<tree> shared:<tree>"), plus "+<digest>" over tracked changes and
 * untracked files under them. A commit that only touches the harness keeps the identity, so a forked or stopped run can be
 * resumed after harness fixes (a plain HEAD refused it). fork/fork_run.py writes the same form. "unknown" when git fails.
 */
export function pluginFingerprint(repoRoot: string): string {
  const git = (...args: string[]) => execFileSync("git", ["-C", repoRoot, ...args], { encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  try {
    const head = CODE_DIRS.map((d) => `${d}:${git("rev-parse", `HEAD:${d}`).trim()}`).join(" ");
    const hash = createHash("sha256");
    hash.update(git("diff", "HEAD", "--binary", "--", ...CODE_DIRS));
    const untracked = git("ls-files", "-o", "--exclude-standard", "-z", "--", ...CODE_DIRS).split("\0").filter(Boolean).sort();
    for (const rel of untracked) {
      hash.update(`\0${rel}\0`);
      try {
        hash.update(fs.readFileSync(path.join(repoRoot, rel)));
      } catch {
        hash.update("unreadable");
      }
    }
    const dirty = hash.digest("hex");
    const clean = createHash("sha256").digest("hex"); // digest of "nothing changed"
    return dirty === clean ? head : `${head}+${dirty.slice(0, 16)}`;
  } catch {
    return "unknown";
  }
}

/** The package hash the pipeline itself computes (lib.brief_package), over the files in `fixtureDir`. Fixed argv, no shell. */
export function packageDigest(repoRoot: string, fixtureDir: string): string {
  const code = "import sys, pathlib; sys.path.insert(0, sys.argv[1]); from lib import brief_package; print(brief_package.package_sha256(pathlib.Path(sys.argv[2])))";
  const out = execFileSync("uv", ["run", "--no-project", "python", "-I", "-c", code, path.join(repoRoot, "shared", "scripts"), fixtureDir], { encoding: "utf8", timeout: 120_000 }).trim();
  if (!/^[0-9a-f]{64}$/.test(out)) throw new Error(`the package hash could not be computed (got "${out.slice(0, 80)}")`);
  return out;
}
