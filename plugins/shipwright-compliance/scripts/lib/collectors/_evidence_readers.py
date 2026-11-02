"""JUnit / Playwright / Vitest parsers for the execution-evidence reader (TT-EV).

Extracted from ``execution_evidence.py`` (ADR-099 300-LOC cap). Each parser maps a
raw runner report to ``{path::name → evidence}`` keyed to the ``test_links``
collector's stable **project_root-relative POSIX** ids. Three real-world joins that
the id must survive, all fail-closed:

* **Path normalization** — Vitest/Jest emit an ABSOLUTE ``testResults[].name`` and a
  per-plugin pytest JUnit emits a ``file`` base relative to the plugin dir, not the
  project root; ``norm_path`` strips an absolute project_root prefix and (when the
  caller knows the runner's subdir) rebases with ``base`` so the id joins.
* **pytest parametrization** — JUnit emits ``test_foo[p0]`` per param but the grammar
  binds ``@covers`` at function level (``path::test_foo``); the ``[…]`` suffix is
  stripped and ``merge_into`` folds the params fail-closed.
* **Playwright multi-project** — a spec has one ``tests[]`` entry PER PROJECT
  (browser); ``results[]`` are retries within a project. Each project is reduced to a
  verdict, then projects are combined FAIL-CLOSED (any project fail ⇒ fail), so a
  chromium pass can never mask a firefox fail.
* **Playwright rootDir** — the JSON reporter writes each spec ``file`` relative to
  ``config.rootDir`` (the testDir), not the project root; with no explicit base the
  report's own absolute ``rootDir`` (when inside the project) is the base. It is
  an absolute host path, so it only helps a report read on the machine that made it.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ._evidence_vocab import entry, merge_into, stronger

# Cap the parsed JUnit size — a hostile/huge report (billion-laughs entity blow-up)
# fails closed to an empty parse rather than exhausting memory (no defusedxml dep).
_MAX_XML_BYTES = 8 * 1024 * 1024
# pytest parametrization: test_foo[p0] → test_foo. From the FIRST "[": a function name holds none, but a
# parameter value may (`test_foo[branches: [main]-x]`), and a match that stops at the first `]` would leave that id unfolded.
_PARAM_SUFFIX = re.compile(r"\[.*\]$", re.DOTALL)


def norm_path(raw: str, root: Path | None, base: str = "") -> str:
    """Normalize a runner-emitted path to project_root-relative POSIX.

    Strips an absolute ``root`` prefix (Vitest's absolute name); a relative path is
    kept and, when ``base`` is supplied (the subdir the runner ran in), rebased under
    it. An absolute path outside ``root`` is left as-is → it won't join → ``not_run``
    (fail-closed, never a false pass).
    """
    s = (raw or "").replace("\\", "/").strip()
    if root is not None and s and Path(raw).is_absolute():
        try:
            s = Path(raw).resolve().relative_to(Path(root).resolve()).as_posix()
        except (ValueError, OSError):
            pass  # absolute but not under root → keep (won't join; fail-closed)
    if s.startswith("./"):
        s = s[2:]
    if base:
        b = base.replace("\\", "/").strip("/")
        if b and s != b and not s.startswith(b + "/"):
            s = f"{b}/{s}"
    return s


def _classname_to_path(classname: str | None) -> str:
    """JUnit fallback when a ``<testcase>`` has no ``file`` attribute.

    Not a rare fallback in practice: this repo's OWN staged evidence
    (``.shipwright/compliance/evidence/junit-05.xml``) confirms pytest's default
    xunit2 report never emits ``file=`` at all, so this is the path ALWAYS taken.

    ``classname`` is dotted module-path segments, optionally followed by ONE OR
    MORE trailing test-CLASS segments for a class-based test —
    ``tests.test_foo.TestBar`` is module ``tests/test_foo.py``, class ``TestBar``;
    ``tests.test_foo.TestOuter.TestInner`` (a nested class) carries two. A
    module-only classname (``tests.test_foo``) has no trailing class segment at
    all, so the two shapes must be told apart before rejoining as a path — a
    plain ``.replace(".", "/")`` mangles the class segment(s) into the path
    (``tests/test_foo/TestBar.py``), which never joins anything and silently
    reads MISSING forever.

    Distinguishing them from the string alone: pytest test-module segments are
    valid Python identifiers under PEP 8 (``test_foo``, lowercase/underscore); a
    test class is conventionally CapWords (``TestBar``). Strip trailing
    CapWords-shaped segments — while 2+ segments remain — before rejoining, so a
    class-based test resolves to its real module file. Best-effort: a module
    segment that itself starts uppercase defeats the heuristic (same class of
    limitation ``norm_path`` already accepts for other id shapes — fail-closed,
    never a false pass, just a MISSING that a differently-shaped id would fix).
    """
    if not classname:
        return ""
    parts = classname.split(".")
    while len(parts) > 1 and parts[-1][:1].isupper():
        parts = parts[:-1]
    return "/".join(parts) + ".py"


def read_junit(text: str, root: Path | None = None, base: str = "") -> dict:
    """Parse a JUnit XML string into ``{path::name → evidence}`` (runner=pytest).

    ``<skipped>`` → skipped/not_run; ``<failure>``/``<error>`` → enabled/fail; else
    enabled/pass. A trailing ``[param]`` suffix is stripped to the function-level id.
    """
    out: dict = {}
    if len(text.encode("utf-8", "ignore")) > _MAX_XML_BYTES:
        return out  # oversized report → fail-closed empty parse
    try:
        node = ET.fromstring(text)
    except ET.ParseError:
        return out
    for tc in node.iter("testcase"):
        name = tc.get("name")
        file = tc.get("file") or _classname_to_path(tc.get("classname"))
        if not name or not file:
            continue
        name = _PARAM_SUFFIX.sub("", name)
        if tc.find("skipped") is not None:
            status, executed = "skipped", "not_run"
        elif tc.find("failure") is not None or tc.find("error") is not None:
            status, executed = "enabled", "fail"
        else:
            status, executed = "enabled", "pass"
        merge_into(out, f"{norm_path(file, root, base)}::{name}", entry(status, executed, "pytest"))
    return out


def read_junit_cases(text: str, root: Path | None = None, base: str = "") -> dict[str, int]:
    """``{folded id → passing <testcase> count}`` — the runner's own unit.

    :func:`read_junit` folds ``test_foo[a]`` / ``test_foo[b]`` into ONE id (the
    fail-closed identity traceability joins on), so ``len(results)`` undercounts what
    pytest prints as "N passed". A runner-reported ``tests_run`` is that case count;
    this keeps the same ids and counts the cases behind each, so a gate can compare
    like with like. Only passing cases count, and ids resolve exactly as ``read_junit``
    resolves them.
    """
    seen: dict[str, set[tuple[str, str]]] = {}
    if len(text.encode("utf-8", "ignore")) > _MAX_XML_BYTES:
        return {}
    try:
        node = ET.fromstring(text)
    except ET.ParseError:
        return {}
    for tc in node.iter("testcase"):
        name = tc.get("name")
        file = tc.get("file") or _classname_to_path(tc.get("classname"))
        if not name or not file:
            continue
        if any(tc.find(tag) is not None for tag in ("skipped", "failure", "error")):
            continue
        tid = f"{norm_path(file, root, base)}::{_PARAM_SUFFIX.sub('', name)}"
        # DISTINCT cases: a concatenated report repeating a row must not count twice
        seen.setdefault(tid, set()).add((tc.get("classname") or "", name))
    return {tid: len(cases) for tid, cases in seen.items()}


def _project_verdict(test: dict) -> tuple[str, str]:
    """Reduce ONE Playwright ``tests[]`` entry (a single project/browser, whose
    ``results[]`` are retries) to a ``(status, executed)`` verdict."""
    results = [r.get("status") for r in (test.get("results") or [])]
    if "passed" in results:  # a retry passed within this project
        return "enabled", "pass"
    if test.get("status") == "skipped" or (results and set(results) <= {"skipped"}):
        return "skipped", "not_run"
    if test.get("status") == "unexpected" or {"failed", "timedOut", "interrupted"} & set(results):
        return "enabled", "fail"
    return "enabled", "not_run"  # no observed result → fail-closed


def _playwright_state(spec: dict) -> tuple[str, str]:
    """Combine every project's verdict FAIL-CLOSED (any project fail ⇒ fail), so a
    chromium pass never masks a firefox fail — mirrors the merge_into precedence."""
    verdict = ("skipped", "not_run")
    for test in spec.get("tests", []) or []:
        verdict = stronger(verdict, _project_verdict(test))
    return verdict


def _playwright_rootdir_base(data: dict, root: Path | None) -> str:
    """Project-relative POSIX path of the report's ``config.rootDir``, or ``""``.

    Playwright writes each spec ``file`` relative to ``config.rootDir`` (the ``testDir``), not to
    the project root, so a config in a sub-folder yields ids that never join the manifest. The
    report carries ``rootDir`` as an ABSOLUTE path; a missing/relative/non-string value, one
    outside ``root``, or ``root`` itself yields ``""`` (⇒ the unchanged historical behavior —
    fail-closed, never a guessed prefix).
    """
    config = data.get("config")
    raw = config.get("rootDir") if isinstance(config, dict) else None
    if root is None or not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
        return ""
    try:
        rel = Path(raw).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return ""
    return "" if rel == "." else rel


def _playwright_path(file: str, root: Path | None, explicit_base: str, derived_base: str) -> str:
    """Project-relative id path of ONE spec ``file``.

    An explicit base keeps ``norm_path``'s historical rebase. A DERIVED base is certain (the file
    IS rootDir-relative), so it is joined unconditionally: ``norm_path``'s "already prefixed"
    heuristic would skip it for ``<rootDir>/<rootDir-name>/x.spec.ts`` and key another test. An
    already absolute file is rebased onto ``root`` by ``norm_path`` and gets no prefix at all.
    A ``..`` segment (a project whose testDir lies outside rootDir) is collapsed; a result that
    still climbs out of the project never joins (fail-closed).
    """
    if explicit_base or not derived_base or Path(file).is_absolute():
        return norm_path(file, root, explicit_base)
    rel = norm_path(file, root)
    return posixpath.normpath(f"{derived_base}/{rel}")


def read_playwright(data: dict, root: Path | None = None, base: str = "") -> dict:
    """Parse Playwright JSON-reporter output into ``{file::title → evidence}``.

    Recurses nested ``suites`` (describe blocks), carrying the file down from the
    enclosing file-suite so a nested spec still keys to its source file. With no explicit
    ``base``, the spec files are rebased under the report's own ``config.rootDir`` (when it
    lies inside ``root``); an explicit ``base`` always wins.
    """
    out: dict = {}
    explicit_base = base
    derived_base = "" if base else _playwright_rootdir_base(data, root)

    def walk(suite: dict, file: str) -> None:
        file = suite.get("file") or file
        for spec in suite.get("specs", []) or []:
            title = spec.get("title")
            if title and file:
                tid = f"{_playwright_path(file, root, explicit_base, derived_base)}::{title}"
                merge_into(out, tid, entry(*_playwright_state(spec), "playwright"))
        for sub in suite.get("suites", []) or []:
            walk(sub, file)

    for suite in data.get("suites", []) or []:
        walk(suite, suite.get("file", ""))
    return out


def read_vitest(data: dict, root: Path | None = None, base: str = "") -> dict:
    """Parse Vitest (Jest-shaped) JSON-reporter output into ``{file::title → evidence}``."""
    out: dict = {}
    for tr in data.get("testResults", []) or []:
        file = tr.get("name")
        if not file:
            continue
        rel = norm_path(file, root, base)
        for a in tr.get("assertionResults", []) or []:
            title = a.get("title")
            if not title:
                continue
            st = a.get("status")
            if st == "passed":
                status, executed = "enabled", "pass"
            elif st == "failed":
                status, executed = "enabled", "fail"
            else:  # skipped | pending | todo → never a pass
                status, executed = "skipped", "not_run"
            merge_into(out, f"{rel}::{title}", entry(status, executed, "vitest"))
    return out
