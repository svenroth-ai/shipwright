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
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ._evidence_vocab import entry, merge_into, stronger

# Cap the parsed JUnit size — a hostile/huge report (billion-laughs entity blow-up)
# fails closed to an empty parse rather than exhausting memory (no defusedxml dep).
_MAX_XML_BYTES = 8 * 1024 * 1024
_PARAM_SUFFIX = re.compile(r"\[[^\]]*\]$")  # pytest parametrization: test_foo[p0] → test_foo


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
    """Best-effort JUnit fallback when a ``<testcase>`` has no ``file`` attribute:
    ``tests.test_auth`` → ``tests/test_auth.py`` (pytest always emits ``file``)."""
    if not classname:
        return ""
    return classname.replace(".", "/") + ".py"


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


def read_playwright(data: dict, root: Path | None = None, base: str = "") -> dict:
    """Parse Playwright JSON-reporter output into ``{file::title → evidence}``.

    Recurses nested ``suites`` (describe blocks), carrying the file down from the
    enclosing file-suite so a nested spec still keys to its source file.
    """
    out: dict = {}

    def walk(suite: dict, file: str) -> None:
        file = suite.get("file") or file
        for spec in suite.get("specs", []) or []:
            title = spec.get("title")
            if title and file:
                tid = f"{norm_path(file, root, base)}::{title}"
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
