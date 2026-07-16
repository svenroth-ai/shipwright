"""Deterministic-cascade tests for the shared backfill engine (traceability TT6).

Covers the signal cascade, the §11-R1 confidence gating for the deterministic
signals, the three orphan categories (§11-R4), idempotency, the introducing-commit
signal, conflict handling, and the no-delete safety rule. The LLM leg + the
cross_component composition with the TT1 collector live in
``test_backfill_llm.py``.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backfill_support import auto_frs, copy_repo, run  # noqa: E402


# --------------------------------------------------------------------------- #
# AC1 — deterministic auto-writes + proposals + orphan categories             #
# --------------------------------------------------------------------------- #

def test_deterministic_auto_writes_and_categories(tmp_path):
    repo = copy_repo(tmp_path)
    # The fixture IS a Shipwright-convention repo, so a unique NN- split may write.
    report = run(repo, apply=True, split_convention=True)
    s = report["summary"]

    assert auto_frs(report) == {"FR-05.02", "FR-06.01"}
    assert s["auto_written"] == 2

    signals = {w["fr"]: set(w["signals"]) for w in report["auto_written"]}
    assert "path_fr_token" in signals["FR-05.02"]
    assert "unique_split" in signals["FR-06.01"]

    dash = (repo / "e2e/flows/FR-05.02-dashboard.spec.ts").read_text(encoding="utf-8")
    arch = (repo / "integration-tests/06-archive.test.ts").read_text(encoding="utf-8")
    assert "// @covers FR-05.02" in dash
    assert "// @covers FR-06.01" in arch

    props = {p["test"]: p for p in report["proposals"]}
    export = props["tests/test_export.py::test_export_orders_to_csv"]
    assert [c["fr"] for c in export["candidates"]] == ["FR-05.01"]
    assert export["candidates"][0]["signals"] == ["title_similarity"]

    orph = report["orphans"]
    assert orph["confirmed_orphan"][0]["tagged_fr"] == "FR-05.09"
    assert orph["confirmed_orphan"][0]["reason"] == "fr_removed"
    assert orph["possible_orphan"][0]["candidate_fr"] == "FR-05.09"
    assert orph["possible_orphan"][0]["reason"] == "fr_removed"
    assert orph["unmapped"] == ["tests/test_misc.py::test_unrelated_helper_returns_value"]


# --------------------------------------------------------------------------- #
# AC3 — idempotency                                                           #
# --------------------------------------------------------------------------- #

def test_idempotent_rerun_adds_no_duplicate_tags(tmp_path):
    repo = copy_repo(tmp_path)
    run(repo, apply=True)
    before = (repo / "e2e/flows/FR-05.02-dashboard.spec.ts").read_bytes()
    report2 = run(repo, apply=True)
    after = (repo / "e2e/flows/FR-05.02-dashboard.spec.ts").read_bytes()

    assert report2["summary"]["auto_written"] == 0
    assert before == after                                   # byte-stable
    assert after.count(b"@covers FR-05.02") == 1             # no duplicate tag


def test_already_tagged_test_is_honoured_not_rewritten(tmp_path):
    repo = copy_repo(tmp_path)
    login = repo / "tests/test_login.py"
    before = login.read_bytes()
    report = run(repo, apply=True)
    assert login.read_bytes() == before                      # never touched
    assert report["summary"]["already_tagged"] >= 1
    assert not any("test_login" in w["test"] for w in report["auto_written"])


# --------------------------------------------------------------------------- #
# Signal (d) — introducing commit's affected_frs                              #
# --------------------------------------------------------------------------- #

def test_unique_commit_signal_auto_writes(tmp_path):
    repo = copy_repo(tmp_path)
    report = run(repo, apply=False, commit_frs={"tests/test_misc.py": ["FR-05.01"]})
    misc = [w for w in report["auto_written"] if "test_misc" in w["test"]]
    assert misc and misc[0]["fr"] == "FR-05.01"
    assert "unique_commit" in misc[0]["signals"]


def test_multi_fr_commit_stays_advisory(tmp_path):
    repo = copy_repo(tmp_path)
    report = run(repo, apply=False,
                 commit_frs={"tests/test_misc.py": ["FR-05.01", "FR-05.02"]})
    # A commit touching several FRs is ambiguous → a proposal, never an auto-write.
    assert not any("test_misc" in w["test"] for w in report["auto_written"])
    misc = next(p for p in report["proposals"] if "test_misc" in p["test"])
    assert {c["fr"] for c in misc["candidates"]} == {"FR-05.01", "FR-05.02"}


def test_two_deterministic_signals_conflict_is_not_written(tmp_path):
    repo = copy_repo(tmp_path)
    # A path carrying TWO distinct active FR tokens is ambiguous — the engine
    # surfaces the conflict, it never guesses one and writes it.
    combo = repo / "e2e/flows/FR-05.01-and-FR-05.02-combo.spec.ts"
    combo.write_text(
        "import { test } from '@playwright/test';\n"
        "test('does two things', async () => {});\n", encoding="utf-8")
    report = run(repo, apply=True)
    assert not any("combo" in w["test"] for w in report["auto_written"])
    p = next(pr for pr in report["proposals"] if "combo" in pr["test"])
    assert p["conflict"] is True
    assert {c["fr"] for c in p["candidates"]} == {"FR-05.01", "FR-05.02"}
    assert "// @covers" not in combo.read_text(encoding="utf-8")     # nothing written


def test_mixed_live_and_dead_tag_surfaces_confirmed_orphan(tmp_path):
    repo = copy_repo(tmp_path)
    # A test tagged with BOTH a live and a removed FR keeps its live coverage but
    # still surfaces the dead tag as a confirmed orphan (never silently skipped).
    mixed = repo / "tests/test_mixed_tags.py"
    mixed.write_text(
        "import pytest\n\n"
        '@pytest.mark.covers("FR-05.01", "FR-05.09")\n'
        "def test_mixed():\n    assert True\n", encoding="utf-8")
    report = run(repo, apply=True)
    conf = report["orphans"]["confirmed_orphan"]
    assert any(o["test"].endswith("::test_mixed") and o["tagged_fr"] == "FR-05.09"
               for o in conf)
    assert mixed.read_text(encoding="utf-8").count("@pytest.mark.covers") == 1  # not rewritten


def test_every_dead_tag_surfaces_as_its_own_confirmed_orphan(tmp_path):
    repo = copy_repo(tmp_path)
    # Two dead tags (one removed, one absent) must BOTH surface — not just the
    # first — so TT7/TT8 triage sees every stale link.
    two = repo / "tests/test_two_dead.py"
    two.write_text(
        "import pytest\n\n"
        '@pytest.mark.covers("FR-05.09", "FR-07.07")\n'
        "def test_two():\n    assert True\n", encoding="utf-8")
    report = run(repo, apply=True)
    conf = [o for o in report["orphans"]["confirmed_orphan"] if "test_two" in o["test"]]
    reasons = {o["tagged_fr"]: o["reason"] for o in conf}
    assert reasons == {"FR-05.09": "fr_removed", "FR-07.07": "fr_absent"}


def test_removed_only_path_token_is_possible_orphan_not_unmapped(tmp_path):
    repo = copy_repo(tmp_path)
    # A deterministic path token pointing at a REMOVED FR (no live match, no title
    # overlap) is a possible orphan — never silently `unmapped` (§11-R4).
    d = repo / "tests" / "FR-05.09"
    d.mkdir()
    (d / "test_legacy_flow.py").write_text("def test_old_flow():\n    assert True\n", encoding="utf-8")
    report = run(repo, apply=False)
    po = [o for o in report["orphans"]["possible_orphan"] if "test_old_flow" in o["test"]]
    assert po and po[0]["candidate_fr"] == "FR-05.09" and po[0]["reason"] == "fr_removed"
    assert "path_fr_token" in po[0]["signals"]
    assert not any("test_old_flow" in w["test"] for w in report["auto_written"])
    assert not any("test_old_flow" in t for t in report["orphans"]["unmapped"])


def test_python_write_adds_a_real_pytest_import_when_absent(tmp_path):
    repo = copy_repo(tmp_path)
    # A pytest file whose only "import pytest" is prose in the docstring — a raw
    # substring check would wrongly skip the import and the emitted decorator
    # would NameError. The engine adds a real import (AST-checked) and tags it.
    f = repo / "tests/test_orders_flow.py"
    f.write_text('"""Mentions import pytest only in prose."""\n\n\ndef test_orders():\n    assert True\n',
                 encoding="utf-8")
    run(repo, apply=True, commit_frs={"tests/test_orders_flow.py": ["FR-05.01"]})
    out = f.read_text(encoding="utf-8")
    assert '@pytest.mark.covers("FR-05.01")' in out
    assert "\nimport pytest\n" in out          # a real import statement was inserted
    ast.parse(out)                              # still valid Python (no NameError shape)


def test_introducing_commit_map_reads_real_git_and_events(tmp_path):
    """Signal (d) end-to-end: a committed test file + an events log mapping its
    introducing commit → an FR drives a unique_commit auto-write (no injection)."""
    repo = copy_repo(tmp_path)

    def _git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)

    _git("init", "-q")
    _git("config", "user.email", "t@example.com")
    _git("config", "user.name", "t")
    _git("add", "tests/test_misc.py")
    _git("commit", "-qm", "add misc")
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    (repo / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": sha, "affected_frs": ["FR-05.01"]}) + "\n",
        encoding="utf-8")

    report = run(repo, apply=False)             # no commit_frs injected → real git+events path
    misc = [w for w in report["auto_written"] if "test_misc" in w["test"]]
    assert misc and misc[0]["fr"] == "FR-05.01"
    assert "unique_commit" in misc[0]["signals"]


# --------------------------------------------------------------------------- #
# Safety — an orphan is surfaced, never deleted; writes are opt-out            #
# --------------------------------------------------------------------------- #

def test_orphan_is_surfaced_never_deleted(tmp_path):
    repo = copy_repo(tmp_path)
    legacy = repo / "e2e/flows/legacy.spec.ts"
    before = legacy.read_bytes()
    run(repo, apply=True)
    assert legacy.exists()                                   # never deleted
    assert legacy.read_bytes() == before                    # its tag left intact


def test_dry_run_writes_no_files(tmp_path):
    repo = copy_repo(tmp_path)
    dash = repo / "e2e/flows/FR-05.02-dashboard.spec.ts"
    before = dash.read_bytes()
    report = run(repo, apply=False, split_convention=True)
    assert dash.read_bytes() == before                       # nothing mutated
    assert auto_frs(report) == {"FR-05.02", "FR-06.01"}      # but still reported


def test_unique_split_is_advisory_without_convention_flag(tmp_path):
    repo = copy_repo(tmp_path)
    # DEFAULT (no --repo-follows-split-convention): a bare NN- prefix must NOT
    # auto-write (it is the Playwright/Cypress execution-order convention on a
    # brownfield repo) — it degrades to a proposal. The explicit FR-token path
    # (FR-05.02) still auto-writes.
    report = run(repo, apply=True)
    assert auto_frs(report) == {"FR-05.02"}
    assert "FR-06.01" not in auto_frs(report)
    arch = repo / "integration-tests/06-archive.test.ts"
    assert "// @covers FR-06.01" not in arch.read_text(encoding="utf-8")   # not written
    combo = next(p for p in report["proposals"] if "06-archive" in p["test"])
    assert "FR-06.01" in {c["fr"] for c in combo["candidates"]}


def test_non_utf8_source_is_skipped_and_recorded(tmp_path):
    repo = copy_repo(tmp_path)
    # A cp1252/latin-1 test file with a deterministic path-token match: apply must
    # NOT crash mid-batch or leave the file half-written — it skips (file intact),
    # records a write_failure, still tags the other files, and writes the report.
    d = repo / "tests" / "FR-05.02"
    d.mkdir()
    bad = d / "test_cp1252.py"
    bad.write_bytes(b"# comment with \xe9 (latin-1)\ndef test_legacy():\n    assert True\n")
    before = bad.read_bytes()
    report = run(repo, apply=True)                # FR-05.02 path token → auto-write attempt
    assert bad.read_bytes() == before             # untouched (no lossy rewrite)
    fails = report["write_failures"]
    assert any("test_cp1252.py" in f["test"] and f["reason"] == "non_utf8_source" for f in fails)
    # a decodable file still got tagged in the same run
    dash = repo / "e2e/flows/FR-05.02-dashboard.spec.ts"
    assert "// @covers FR-05.02" in dash.read_text(encoding="utf-8")


def test_crlf_line_endings_preserved_on_insert(tmp_path):
    repo = copy_repo(tmp_path)
    dash = repo / "e2e/flows/FR-05.02-dashboard.spec.ts"
    dash.write_bytes(dash.read_bytes().replace(b"\n", b"\r\n"))
    run(repo, apply=True)
    out = dash.read_bytes()
    assert b"// @covers FR-05.02\r\n" in out
    assert out.count(b"\n") == out.count(b"\r\n")             # no lone LF introduced


def test_report_is_deterministically_ordered_and_written(tmp_path):
    repo = copy_repo(tmp_path)
    r1 = run(repo, apply=False)
    r2 = run(copy_repo(tmp_path / "b"), apply=False)
    # Machine-readable report is stable across runs (AC3; TT7/TT8 consume it),
    # ignoring the volatile generated_at metadata field.
    for r in (r1, r2):
        r["generated_at"] = "X"
    assert r1["auto_written"] == r2["auto_written"]
    assert r1["proposals"] == r2["proposals"]
    assert r1["orphans"] == r2["orphans"]

    from _backfill_support import bf
    json_path, md_path = bf.write_report(r1, tmp_path / "out")
    assert json_path.exists() and md_path.exists()
    assert "FR-05.02" in md_path.read_text(encoding="utf-8")
