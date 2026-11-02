"""Show what the operator would see for a new promise: the model's plain wording and area suggestions, validated by code.

    uv run shared/scripts/tools/ac_suggest.py --project-root . --base-ref origin/main --promise-file promise.txt [--no-cache]

Prints JSON: ``suggestion`` (``source`` model|fallback, the ``reason`` for a fallback, the original and the plain wording,
the model id, the prompt sha) and ``question`` (exactly the text the operator is asked). The model is a display aid only:
it never changes the AC text that is frozen. It runs through the existing OpenRouter transport (the cheap model the PR
review uses); no key, an opt-out (``external_review.feedback_iterations: 0``) or any failure gives the deterministic
wording, never an error. The promise and catalog excerpts go to the external provider, like plan reviews do.

Exit codes: 0 always when the catalog could be read (a fallback is not an error); 2 an input problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_catalog import load_catalog  # noqa: E402
from lib.ac_decision import render_question  # noqa: E402
from lib.ac_suggest import suggest  # noqa: E402
from lib.ac_surface import merge_base  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--base-ref", required=True)
    ap.add_argument("--promise-file", required=True, help="the agent's promise text (a file, never a command line)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)
    try:
        promise = " ".join(Path(args.promise_file).read_text(encoding="utf-8-sig").split())
        cat = load_catalog(args.project_root, merge_base(args.project_root, args.base_ref))
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"error": f"cannot read the inputs: {exc}"}), file=sys.stderr)
        return 2
    sugg = suggest(promise, cat, args.project_root, use_cache=not args.no_cache)
    question = render_question({"kind": "add", "new_text": promise}, cat, sugg)
    print(json.dumps({"suggestion": sugg, "question": question}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
