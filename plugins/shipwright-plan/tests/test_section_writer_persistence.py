"""Section-writer persistence regression tests (Campaign 2026-07-07, SS4).

Root cause fixed: the section-writer had no Write tool, so persistence was
delegated entirely to the write-section-on-stop SubagentStop hook (transcript
scraping). When the hook did not fire, the output was lost. The fix gives the
agent a WRITE PATH (it persists its own section file) and demotes the hook to a
non-blocking fallback that never false-blocks a successful direct write.

Pins:
  * the agent declares a Write path + a direct-write instruction;
  * the hook is a no-op success when the section file already exists on disk
    (direct write) — it never blocks and never clobbers;
  * the hook salvages from the transcript only when the file is missing;
  * the hook NEVER emits a blocking payload, whatever the failure.

The hook is loaded IN-PROCESS (importlib) — not via subprocess — so the
diff-coverage gate instruments the changed lines.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
AGENT_MD = PLUGIN_ROOT / "agents" / "section-writer.md"
HOOK_PATH = PLUGIN_ROOT / "scripts" / "hooks" / "write-section-on-stop.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("write_section_on_stop", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()


def _frontmatter(md: str) -> dict[str, str]:
    _, fm, _body = md.split("---", 2)
    out: dict[str, str] = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


# --- agent owns persistence (the root-cause fix) --------------------------- #

def test_section_writer_declares_write_path():
    fm = _frontmatter(AGENT_MD.read_text(encoding="utf-8"))
    tools = {t.strip() for t in fm.get("tools", "").split(",")}
    assert "Write" in tools, f"section-writer must own persistence, got {tools}"


def test_section_writer_instructs_direct_write():
    body = AGENT_MD.read_text(encoding="utf-8").lower()
    assert "write" in body and "sections/" in body
    assert "not rely on a hook" in body  # do NOT rely on a hook to persist


# --- hook drivers ---------------------------------------------------------- #

def _transcript(tmp_path: Path, lines: list[dict]) -> str:
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return str(p)


def _run_hook(monkeypatch, payload: dict, planning_dir):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    if planning_dir is not None:
        monkeypatch.setenv("SHIPWRIGHT_PLANNING_DIR", planning_dir)
    else:
        monkeypatch.delenv("SHIPWRIGHT_PLANNING_DIR", raising=False)
    rc = hook.main()
    return rc, err.getvalue()


def test_hook_noop_when_section_file_exists(tmp_path, monkeypatch):
    # Direct write happened: file exists. Hook confirms, does not clobber, does not block.
    planning = tmp_path / "plandir"
    (planning / "sections").mkdir(parents=True)
    section = planning / "sections" / "01-auth.md"
    section.write_text("# Section: 01-auth\noriginal direct-write content\n", encoding="utf-8")

    # Transcript names the section but has NO scrapeable '# Section:' block — the
    # direct-writer's final message is just a confirmation.
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"write section 01-auth to planning_dir={planning}"},
        {"role": "assistant", "content": "Wrote sections/01-auth.md"},
    ])
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript}, str(planning))
    assert rc == 0
    assert "direct-write confirmed" in err
    # Never clobbered the direct write:
    assert "original direct-write content" in section.read_text(encoding="utf-8")


def test_hook_salvages_when_file_missing(tmp_path, monkeypatch):
    planning = tmp_path / "plandir"
    planning.mkdir()
    content = "# Section: 02-ui\n\n## Overview\nsalvaged from transcript\n"
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": "write section 02-ui"},
        {"role": "assistant", "content": content},
    ])
    rc, _err = _run_hook(monkeypatch, {"transcript_path": transcript}, str(planning))
    assert rc == 0
    out_file = planning / "sections" / "02-ui.md"
    assert out_file.exists()
    assert "salvaged from transcript" in out_file.read_text(encoding="utf-8")


def test_hook_refuses_salvage_write_to_untrusted_inferred_dir(tmp_path, monkeypatch):
    # File missing; transcript carries a valid section + an inferred planning dir
    # that is OUTSIDE the project tree (cwd), and SHIPWRIGHT_PLANNING_DIR is UNSET
    # → refuse to write (path-traversal / write-outside-tree defense).
    planning = tmp_path / "inferred"  # tmp_path is outside the pytest cwd
    planning.mkdir()
    content = "# Section: 03-x\n\n## Overview\nbody\n"
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"write section 03-x planning_dir={planning}"},
        {"role": "assistant", "content": content},
    ])
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript}, None)  # env unset
    assert rc == 0
    assert "outside the project tree" in err
    assert not (planning / "sections").exists()


# --- salvage_write_dir safe-target selection ------------------------------- #

def test_salvage_write_dir_prefers_env(tmp_path):
    assert hook.salvage_write_dir("/env/dir", "/some/inferred", str(tmp_path)) == "/env/dir"


def test_salvage_write_dir_allows_inferred_inside_project(tmp_path):
    inside = tmp_path / "plandir"
    inside.mkdir()
    assert hook.salvage_write_dir("", str(inside), str(tmp_path)) == str(inside)


def test_salvage_write_dir_rejects_inferred_outside_project(tmp_path):
    outside = tmp_path.parent / "elsewhere-outside"
    assert hook.salvage_write_dir("", str(outside), str(tmp_path)) is None


def test_salvage_write_dir_none_when_no_dir_at_all(tmp_path):
    assert hook.salvage_write_dir("", "", str(tmp_path)) is None


# --- extracted helpers ----------------------------------------------------- #

def test_resolve_planning_dir_env_wins(monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_PLANNING_DIR", "/env/planning")
    assert hook.resolve_planning_dir([]) == "/env/planning"


def test_resolve_planning_dir_infers_from_transcript(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_PLANNING_DIR", raising=False)
    entries = [{"role": "user", "content": "planning_dir=.shipwright/planning/foo"}]
    assert hook.resolve_planning_dir(entries) == ".shipwright/planning/foo"


def test_resolve_planning_dir_empty_when_absent(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_PLANNING_DIR", raising=False)
    assert hook.resolve_planning_dir([{"role": "user", "content": "no dir here"}]) == ""


def test_is_section_document_rejects_all_blank():
    assert hook.is_section_document("   \n\n\t\n") is False


def test_existing_section_file_none_without_inputs():
    assert hook.existing_section_file("", None) is None


def test_is_within_handles_realpath_error(monkeypatch):
    def boom(_):
        raise OSError("boom")
    monkeypatch.setattr("os.path.realpath", boom)
    assert hook._is_within("/a", "/b") is False


def test_hook_empty_transcript_never_blocks(tmp_path, monkeypatch):
    # No file on disk + empty transcript → cannot salvage; must still exit 0.
    monkeypatch.setattr(hook, "read_transcript_with_retry", lambda *a, **k: [])
    transcript = _transcript(tmp_path, [{"role": "user", "content": "x"}])
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript}, str(tmp_path))
    assert rc == 0
    assert "transcript empty" in err


def test_hook_refuses_salvage_of_non_section_document(tmp_path, monkeypatch):
    # Content mentions '# Section:' but NOT as the leading header → not a section
    # document; the fallback must not persist arbitrary prose.
    planning = tmp_path / "plandir"
    planning.mkdir()
    content = "Some preamble chatter.\n# Section: 04-y\nbody\n"
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": "write section 04-y"},
        {"role": "assistant", "content": content},
    ])
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript}, str(planning))
    assert rc == 0
    assert "not a section document" in err
    assert not (planning / "sections").exists()


def test_hook_never_blocks_when_nothing_salvageable(tmp_path, monkeypatch):
    planning = tmp_path / "plandir"
    planning.mkdir()
    # No section name, no '# Section:' block, file missing → cannot salvage.
    transcript = _transcript(tmp_path, [
        {"role": "assistant", "content": "I could not complete the task."},
    ])
    rc, _err = _run_hook(monkeypatch, {"transcript_path": transcript}, str(planning))
    assert rc == 0  # NEVER blocks — /shipwright-plan Step 7 check-sections is the gate
    sections = planning / "sections"
    assert not sections.exists() or not list(sections.glob("*.md"))


def test_hook_never_blocks_on_bad_payload(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not valid json"))
    monkeypatch.setattr("sys.stderr", io.StringIO())
    assert hook.main() == 0


def test_hook_never_blocks_on_missing_transcript_path(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"foo": "bar"})))
    monkeypatch.setattr("sys.stderr", io.StringIO())
    assert hook.main() == 0
