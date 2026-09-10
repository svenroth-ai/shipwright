"""Write one requirement's grill-trace record (schema:
``shared/grill-trace-format.md``) to a target project's planning tree.

``shared/requirement-elicitation.md`` §9 fires the moment a requirement's
shared understanding is confirmed with the person; this is that producer —
the ONE code path that writes a grill-trace file, one JSON document per
elicited requirement at
``{planning_dir}/grill-traces/<requirement_key>.json``. It is written
**live, during the interview** (per the design at
``.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md``),
not batched after the fact — call it in the same turn the confirmation
happens, mirroring ``write_context_term.py``'s "capture as you go" contract.

Usage — **``--payload-file`` is the sanctioned way to pass free text from an
interview** (same precedent as ``write_context_term.py``'s final review
finding): the caller writes the full record as JSON via the Write tool
(never a shell command), so no shell ever parses interview-dictated text:

    uv run shared/scripts/tools/write_grill_trace.py \\
        --project-root . --payload-file /path/to/grill-trace-payload.json

where ``payload.json`` is the full record shape documented in
``shared/grill-trace-format.md`` §2 (``requirement_key``,
``requirement_text``, ``surface``, ``evidence``, ``dimensions``,
``fit_criterion``, ``glossary_delta``, ``confirmed_by``, ``terms_used``).

**Idempotent:** re-running with the same ``requirement_key`` overwrites that
one file in place (a requirement revisited later during the same interview
just updates its trace) — never a second file, never touches any other
requirement's trace. Locked per-file (mirrors ``write_context_term.py``'s
``file_lock`` discipline) even though cross-requirement contention is
structurally impossible (each requirement owns its own file) — a
same-requirement re-entrant call during a fast-moving interview is not.

Exit codes: 0 on success — ``status`` is ``created`` or ``updated``. Exit 1
on a lock timeout, I/O error, or a rejected/malformed payload
(``grill_trace_format.GrillTraceError``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402

from tools._write_grill_trace_cli import PayloadError, build_arg_parser, load_payload_file  # noqa: E402
from tools.grill_trace_format import GrillTraceError, parse_trace, trace_path  # noqa: E402


def write_trace(planning_dir: Path, payload: dict, *, lock_timeout: float) -> dict[str, object]:
    """Validate ``payload`` and write it to
    ``{planning_dir}/grill-traces/<requirement_key>.json``. Raises
    :class:`GrillTraceError` on a malformed payload before any I/O happens."""
    trace = parse_trace(payload)
    directory = trace_path(planning_dir, trace.requirement_key).parent
    directory.mkdir(parents=True, exist_ok=True)
    path = trace_path(planning_dir, trace.requirement_key)
    lock_path = path.with_suffix(path.suffix + ".lock")

    existed = path.exists()
    new_content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with file_lock(lock_path, timeout_seconds=lock_timeout):
        durable_atomic_write(path, new_content)

    return {
        "status": "updated" if existed else "created",
        "path": str(path),
        "requirement_key": trace.requirement_key,
    }


def main() -> int:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    parser = build_arg_parser(__doc__.split("\n")[0])
    args = parser.parse_args()

    try:
        payload = load_payload_file(args.payload_file)
    except PayloadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"ERROR: --project-root does not exist: {project_root}", file=sys.stderr)
        return 1
    if args.planning_dir:
        planning_dir = Path(args.planning_dir).resolve()
    else:
        planning_dir = project_root / ".shipwright" / "planning"
    # planning_dir/grill-traces/ is created on demand in write_trace() — the
    # planning dir itself need not pre-exist for this call alone.

    try:
        result = write_trace(planning_dir, payload, lock_timeout=args.lock_timeout)
    except (GrillTraceError, LockTimeout, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
