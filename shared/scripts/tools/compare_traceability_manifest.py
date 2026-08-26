#!/usr/bin/env python3
"""Compare a committed `test-traceability.json` against a freshly regenerated
one (iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC1).

Two-tier comparison, because the manifest mixes fields that are reproducible
across CI/local regens with fields that legitimately are not:

  * **Structural tier (enforced):** everything except `generated_at` /
    `source_commit` at the top level, and except the entire `tests` map and
    `coverage` map per requirement. Both are execution-derived — which tests
    a run *collected* depends on OS/marker selection
    (`shared/scripts/tools/suite_units.py`), and `coverage` is computed
    straight from `tests`
    (`_test_links_requirements.py::_cov_status`) — so neither can be
    compared structurally without reintroducing the platform false-positive
    this tool exists to avoid. A structural difference is real drift: the
    regenerated manifest disagrees with the committed one on something that
    should never depend on which machine or interpreter produced it.

  * **Execution tier (reported only, never gates):** for each requirement's
    `tests` map, per layer, test ids present in BOTH manifests are compared
    on `status`/`executed` and any disagreement is reported; ids present in
    only one manifest are reported separately as platform-selection
    differences. Neither ever affects the exit code.

Exit codes: 0 = no structural drift · 1 = structural drift found (advisory —
the CI step that calls this with `--check` reports it, never fails the
build, until the gate has proven itself over several consecutive green PRs)
· 2 = usage or runtime error (missing file, malformed JSON, a manifest
missing a required field) — always surfaced, never silently swallowed.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_STRUCTURAL_DRIFT = 1
EXIT_ERROR = 2

_TOP_LEVEL_EXECUTION_KEYS = {"generated_at", "source_commit"}
_REQUIREMENT_EXECUTION_KEYS = {"tests", "coverage"}

_REQUIRED_TOP_KEYS = {
    "schema_version",
    "collector_version",
    "generated_at",
    "source_commit",
    "spec_hash",
    "requirements",
    "orphans",
    "invalid_tags",
    "invalid_layers",
    "untagged_tests",
}
_REQUIRED_REQUIREMENT_KEYS = {
    "id",
    "spec_path",
    "title",
    "priority",
    "status",
    "required_layers",
    "required_layers_source",
    "tests",
    "coverage",
}


class ManifestError(Exception):
    """A manifest file could not be read, parsed, or is missing a required field."""


def _load(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path} is not valid JSON: {exc}") from exc
    _validate(data, path)
    return data


def _validate(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: top-level document must be an object")
    missing = _REQUIRED_TOP_KEYS - data.keys()
    if missing:
        raise ManifestError(f"{path}: missing top-level field(s): {sorted(missing)}")
    requirements = data["requirements"]
    if not isinstance(requirements, dict):
        raise ManifestError(f"{path}: 'requirements' must be an object")
    for req_id, node in requirements.items():
        if not isinstance(node, dict):
            raise ManifestError(f"{path}: requirements[{req_id!r}] must be an object")
        missing = _REQUIRED_REQUIREMENT_KEYS - node.keys()
        if missing:
            raise ManifestError(
                f"{path}: requirements[{req_id!r}] missing field(s): {sorted(missing)}"
            )
        _validate_tests_shape(node["tests"], req_id, path)


def _validate_tests_shape(tests: Any, req_id: str, path: Path) -> None:
    """`tests` feeds `execution_report()`'s `t["id"]` lookups directly — a shape
    surprise there (external review: `null`, a non-list layer, a record with no
    `id`) must fail here with a named field, not as an unhandled
    AttributeError/TypeError/KeyError three calls downstream."""
    if not isinstance(tests, dict):
        raise ManifestError(f"{path}: requirements[{req_id!r}].tests must be an object")
    for layer, records in tests.items():
        if not isinstance(records, list):
            raise ManifestError(
                f"{path}: requirements[{req_id!r}].tests[{layer!r}] must be a list"
            )
        for i, record in enumerate(records):
            if not isinstance(record, dict) or "id" not in record:
                raise ManifestError(
                    f"{path}: requirements[{req_id!r}].tests[{layer!r}][{i}] "
                    f"must be an object with an 'id' field"
                )


def _structural_view(data: dict[str, Any]) -> dict[str, Any]:
    view = {k: v for k, v in data.items() if k not in _TOP_LEVEL_EXECUTION_KEYS}
    view["requirements"] = {
        req_id: {
            k: v for k, v in node.items() if k not in _REQUIREMENT_EXECUTION_KEYS
        }
        for req_id, node in data["requirements"].items()
    }
    return view


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def structural_diff(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Unified diff of the two manifests' structural views; "" iff they agree."""
    old_text = _dumps(_structural_view(old))
    new_text = _dumps(_structural_view(new))
    if old_text == new_text:
        return ""
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="committed (structural)",
            tofile="regenerated (structural)",
        )
    )


def execution_report(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Report-only diff over each requirement's `tests` map. Never gates."""
    report: dict[str, Any] = {}
    old_reqs = old.get("requirements", {})
    new_reqs = new.get("requirements", {})
    for req_id in sorted(set(old_reqs) | set(new_reqs)):
        old_tests = old_reqs.get(req_id, {}).get("tests", {})
        new_tests = new_reqs.get(req_id, {}).get("tests", {})
        req_diff: dict[str, Any] = {}
        for layer in sorted(set(old_tests) | set(new_tests)):
            old_by_id = {t["id"]: t for t in old_tests.get(layer, [])}
            new_by_id = {t["id"]: t for t in new_tests.get(layer, [])}
            shared = set(old_by_id) & set(new_by_id)
            only_old = sorted(set(old_by_id) - set(new_by_id))
            only_new = sorted(set(new_by_id) - set(old_by_id))
            disagreements = []
            for test_id in sorted(shared):
                o, n = old_by_id[test_id], new_by_id[test_id]
                if o.get("status") != n.get("status") or o.get("executed") != n.get("executed"):
                    disagreements.append(
                        {
                            "id": test_id,
                            "committed": {"status": o.get("status"), "executed": o.get("executed")},
                            "regenerated": {"status": n.get("status"), "executed": n.get("executed")},
                        }
                    )
            if disagreements or only_old or only_new:
                req_diff[layer] = {
                    "shared_id_disagreements": disagreements,
                    "platform_only_in_committed": only_old,
                    "platform_only_in_regenerated": only_new,
                }
        if req_diff:
            report[req_id] = req_diff
    return report


def compare(old: dict[str, Any], new: dict[str, Any]) -> tuple[int, str, dict[str, Any]]:
    s_diff = structural_diff(old, new)
    e_report = execution_report(old, new)
    exit_code = EXIT_STRUCTURAL_DRIFT if s_diff else EXIT_OK
    return exit_code, s_diff, e_report


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--check",
        action="store_true",
        required=True,
        help="required: this tool only ever compares, it never writes; the flag "
        "makes that explicit at the call site (matches ci.yml's invocation).",
    )
    ap.add_argument("--committed", required=True, type=Path, help="the committed manifest")
    ap.add_argument("--regenerated", required=True, type=Path, help="the freshly regenerated manifest")
    return ap


def main_with_output(argv: list[str]) -> tuple[int, str]:
    """Runs the comparison and returns (exit_code, everything that would go to stdout)."""
    parser = _build_parser()
    lines: list[str] = []
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_ERROR
        return (code if code != 0 else EXIT_ERROR) or EXIT_ERROR, "\n".join(lines)

    try:
        old = _load(args.committed)
        new = _load(args.regenerated)
    except ManifestError as exc:
        lines.append(f"ERROR: {exc}")
        return EXIT_ERROR, "\n".join(lines)

    exit_code, s_diff, e_report = compare(old, new)

    if exit_code == EXIT_OK:
        lines.append(
            "test-traceability.json: structural fields match the regenerated manifest."
        )
    else:
        lines.append(
            "STRUCTURAL DRIFT — the committed manifest disagrees with a fresh "
            "regeneration on a field that should never depend on platform or "
            "marker selection:\n"
        )
        lines.append(s_diff)

    if e_report:
        lines.append(
            "\nExecution-tier differences (reported only, never gating — "
            "expected to vary by OS/marker selection):"
        )
        lines.append(json.dumps(e_report, indent=2, sort_keys=True))

    return exit_code, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    exit_code, output = main_with_output(sys.argv[1:] if argv is None else argv)
    print(output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
