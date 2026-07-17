"""Aggregator no longer duplicates the F2 run_id bullet as a second ADR-NNN line.

Canonical anchor = run_id (iterate-2026-07-17-arch-doc-refresh-harden): the
iterate flow hand-writes a run_id-keyed bullet at F2 (F11's
``check_architecture_documented`` enforces its presence), so folding the drop at
release must NOT append a second ``ADR-NNN`` bullet to the always-loaded
``## Architecture Updates`` section — that duplication was the inconsistency the
user reported. The ADR<->run_id mapping still lands in ``decision_log.md`` via
``format_entry``'s ``**Run-ID:**`` line. The direct path (``append_decision`` —
build/plan/project/test/deploy) is untouched and stays the sole, non-dup
appender for those phases, now emitting the full canonical bullet.
"""

from __future__ import annotations

from pathlib import Path

from tools.aggregate_decisions import aggregate
from tools.write_decision_drop import write_decision_drop
from tools.write_decision_log import DECISION_LOG_HEADER, append_decision


def _seed(tmp_path: Path, arch_body: str = "") -> tuple[Path, Path]:
    ad = tmp_path / ".shipwright" / "agent_docs"
    ad.mkdir(parents=True, exist_ok=True)
    dlog = ad / "decision_log.md"
    dlog.write_text(DECISION_LOG_HEADER, encoding="utf-8")
    arch = ad / "architecture.md"
    arch.write_text(
        "# Architecture\n\n## Architecture Updates\n" + arch_body, encoding="utf-8"
    )
    return dlog, arch


def test_documented_run_id_appends_zero_arch_lines(tmp_path: Path):
    run_id = "iterate-2026-07-17-example"
    # The F2 run_id bullet is ALREADY present in architecture.md.
    dlog, arch = _seed(
        tmp_path,
        f"- **{run_id}** (2026-07-17): Component — did a thing. "
        f"→ decision_log (Run-ID)\n",
    )
    before = arch.read_text(encoding="utf-8")
    write_decision_drop(
        tmp_path, run_id=run_id, section="Iterate — x", title="Refactor",
        context="c", decision="d", consequences="k",
        architecture_impact="component",
    )
    aggregate(tmp_path)
    after = arch.read_text(encoding="utf-8")
    # architecture.md is byte-unchanged — no duplicate ADR-NNN bullet.
    assert after == before, after
    assert "ADR-" not in after.split("## Architecture Updates", 1)[1]
    # But the ADR + Run-ID linkage DID land in decision_log.md.
    dl = dlog.read_text(encoding="utf-8")
    assert "ADR-001" in dl
    assert f"**Run-ID:** {run_id}" in dl


def test_undocumented_run_id_appends_one_canonical_bullet(tmp_path: Path):
    run_id = "iterate-2026-07-17-orphan"
    _, arch = _seed(tmp_path, "")  # run_id NOT present -> fallback append
    write_decision_drop(
        tmp_path, run_id=run_id, section="Iterate — x", title="Orphan change",
        context="c", decision="d", consequences="k",
        architecture_impact="component",
    )
    aggregate(tmp_path)
    body = arch.read_text(encoding="utf-8").split("## Architecture Updates", 1)[1]
    assert body.count("- **ADR-001**") == 1
    assert "Component — Orphan change. → decision_log (ADR-001)" in body


def test_direct_path_appends_one_canonical_bullet(tmp_path: Path):
    # The direct build/plan/etc. path is single-entry and non-dup; it must keep
    # working AND now emit the full canonical bullet (Impact word + arrow).
    _, arch = _seed(tmp_path, "")
    append_decision(
        tmp_path, section_ref="Build — x", commit_hash="abc",
        context="c", decision="Did a direct thing.", consequences="ok",
        title="Direct thing", architecture_impact="component",
    )
    body = arch.read_text(encoding="utf-8").split("## Architecture Updates", 1)[1]
    assert body.count("- **ADR-001**") == 1
    assert "Component — Direct thing. → decision_log (ADR-001)" in body


def test_run_id_only_in_prose_still_appends(tmp_path: Path):
    # Section-scoped skip: the run_id appears only in PROSE (a Data Flow line),
    # NOT as a bullet in ## Architecture Updates — so the aggregator must still
    # append the canonical ADR bullet rather than wrongly skipping on a whole-file
    # match (external-review Gemini/OpenAI).
    run_id = "iterate-2026-07-17-prose-only"
    ad = tmp_path / ".shipwright" / "agent_docs"
    ad.mkdir(parents=True, exist_ok=True)
    (ad / "decision_log.md").write_text(DECISION_LOG_HEADER, encoding="utf-8")
    (ad / "architecture.md").write_text(
        f"# A\n\n## Data Flow\nThe {run_id} change reworked the widget.\n\n"
        "## Architecture Updates\n",
        encoding="utf-8",
    )
    write_decision_drop(
        tmp_path, run_id=run_id, section="Iterate — x", title="Prose only",
        context="c", decision="d", consequences="k",
        architecture_impact="component",
    )
    aggregate(tmp_path)
    body = (ad / "architecture.md").read_text(encoding="utf-8").split(
        "## Architecture Updates", 1
    )[1]
    assert body.count("- **ADR-001**") == 1
    assert "Component — Prose only. → decision_log (ADR-001)" in body
