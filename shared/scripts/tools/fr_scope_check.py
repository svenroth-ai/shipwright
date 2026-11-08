"""Spec-time FR scope check: may `/shipwright-project` call this spec's requirements finished? (atomic-frs U1)

    uv run shared/scripts/tools/fr_scope_check.py --spec .shipwright/planning/01-core/spec.md

Prints every FR with a problem and exits 1 if there is any: a spec (or file) that is empty, unreadable or has no requirement
this check can read; a Must requirement with no criteria; a file path or code symbol in a criterion. Everything else (a
criterion not in Given/when/then form, an HTTP verb or ADR number, a name joining two capabilities with "and") is
printed as a prompt and never changes the exit code. The capability test (one plain sentence without "and" per group of criteria) stays the skill's AI judgement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.fr_scope_check import check_spec  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--spec", required=True, nargs="+", help="one or more spec.md files")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    found: list[dict] = []
    for spec in args.spec:
        try:
            text = Path(spec).read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:  # missing file, a directory, not UTF-8: a clean message, not a traceback
            found.append({"spec": spec, "fr": "(whole spec)", "problems": [f"cannot read the file: {type(exc).__name__}"], "prompts": []})
            continue
        found += [{"spec": spec, **r} for r in check_spec(text)]
    bad = [r for r in found if r["problems"]]
    if args.json:
        print(json.dumps(found, indent=2))
        return 1 if bad else 0
    for r in found:
        print(f"{r['spec']}: {r['fr']}")
        for line in r["problems"]:
            print(f"  - {line}")
        for line in r["prompts"]:
            print(f"  ? {line}")
    if bad:
        print(f"\n{len(bad)} requirement(s) not finished. Fix them, then re-run.")
    else:
        print("every requirement passes the scope form checks" + (" (prompts above are for the capability test)" if found else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
