"""The behaviours this corpus freezes as WRONG, on purpose.

Read this before "fixing" anything that looks broken in ``golden.json``.

A golden file cannot carry comments, so a future contributor could look at a
surprising cell, conclude it is a mistake, and correct it -- silently destroying
the baseline that campaign steps S2-S6 are measured against. This module is the
missing justification. Each entry names what is wrong, why it is NOT fixed here,
and which campaign step flips it; ``regen_golden.py`` embeds a copy into
``golden.json`` so the reader of the data file is pointed back here.

The two verdicts the campaign SPEC names are FV-1 and FV-2. FV-3, FV-4 and FV-5
were found while building this harness and are NOT in the SPEC; they have been
added to S4's acceptance criteria and filed as a triage anchor so they cannot be
lost if S4 is descoped.
"""

from __future__ import annotations

FROZEN_BUGS: dict[str, dict] = {
    "FV-1": {
        "what": "A spec that parses to ZERO rows makes traceability check T1 "
                "SKIP rather than FAIL.",
        "mechanism":
            "traceability_checks.check_t1_all_spec_frs_mapped guards on "
            "`if not requirements:`. collect_requirements_from_planning returns "
            "[] for BOTH 'no planning directory' and 'spec present, every row "
            "failed to parse', so the guard cannot distinguish them and the "
            "FAIL branch below is unreachable on a zero-row parse. A table with "
            "its columns reordered is the realistic trigger: "
            "drift_parsers._FR_TABLE_RE pins Must|Should|May to data column 3.",
        "why_not_fixed":
            "This harness exists to prove S2-S4 are behaviour-preserving. "
            "Fixing the baseline here would leave nothing to measure against.",
        "flipped_by": "S4 (one header-driven row parser -- column order stops "
                      "being load-bearing, so a zero-row parse of a populated "
                      "spec becomes impossible)",
        "cells": [
            ("parse.drift_parsers.parse_fr_table", "mixed-shape",
             ".shipwright/planning/06-reordered/spec.md"),
        ],
        "also_pinned_in": "test_requirements_corpus_false_verdicts.py",
    },
    "FV-2": {
        "what": "An empty requirement set reads GREEN across the audit plane -- "
                "'no requirements' is treated as 'nothing to audit'.",
        "mechanism":
            "Ten Tier-1 guards. The sharpest is NOT the one the campaign SPEC "
            "names: _group_d_traceability emits "
            "('pass', 'LOW', 'every active FR is covered at its required "
            "layers') -- a POSITIVE coverage claim over the empty set. Every "
            "other site at least says 'skip'. Note the repo already knows how "
            "to treat emptiness as a defect elsewhere (adopt_compliance A2 "
            "FAILs, campaign_status raises, design_checks returns not-ok), so "
            "this is a local inconsistency, not a house style.",
        "why_not_fixed": "Same as FV-1 -- it is the baseline.",
        "flipped_by": "S6 (one catalog at one path: 'no requirements found' "
                      "stops being a legitimate state)",
        "cells": [],  # pinned as prose, not as a matrix cell
        "also_pinned_in": "test_requirements_corpus_false_verdicts.py",
    },
    "FV-3": {
        "what": "The RTM can display the WRONG requirement text.",
        "mechanism":
            "drift_parsers and rtm are header-blind. When a row carries more "
            "cells than its header declares, regex group 4 fires and a LATER "
            "column is read as the requirement body. Given a 3-column header "
            "and the row `| FR-07.01 | ok | Should | extra | cells |`, both "
            "return text 'extra' instead of 'ok'. This is live wrong data in a "
            "shipped audit artifact, not merely a parse divergence.",
        "why_not_fixed":
            "Not in the campaign SPEC; found while building this harness. "
            "Fixing it here would change RTM output in the same commit that is "
            "supposed to establish the baseline.",
        "flipped_by": "S4 (a header-driven reader selects by column NAME, so a "
                      "row wider than its header can no longer shift the body)",
        "cells": [
            ("parse.drift_parsers.parse_fr_table", "mixed-shape",
             ".shipwright/planning/07-header-blind/spec.md"),
        ],
        "found_by": "iterate-2026-07-18-requirements-golden-corpus",
    },
    "FV-4": {
        "what": "Group I silently audits NOTHING when a table header says 'FR' "
                "instead of 'ID'.",
        "mechanism":
            "group_i._column_map requires cells[0] == 'id' exactly. On the "
            "traceability-fixture shape `FR | Description | Priority | Layers` "
            "it returns None, the column mapping stays None, and every row in "
            "the file is dropped. All four naming-hygiene checks then report "
            "against zero rows -- and zero rows is itself a green state (FV-2).",
        "why_not_fixed": "Not in the campaign SPEC; found here. Same baseline "
                         "argument as FV-3.",
        "flipped_by": "S4 (one header-driven reader, one accepted id column)",
        "cells": [
            ("parse.group_i._scan_one_spec", "mixed-shape",
             ".shipwright/planning/05-fixture-fr/spec.md"),
        ],
        "found_by": "iterate-2026-07-18-requirements-golden-corpus",
    },
    "FV-5": {
        "what": "Group I drops requirement rows that appear after any heading.",
        "mechanism":
            "group_i._scan_one_spec resets `mapping = None` at EVERY heading, "
            "table-related or not. An FR row under a later heading without a "
            "repeated header row is silently dropped. In the `edge` fixture "
            "group_i loses FR-01.20 (under '## Next'); all four other parsers "
            "keep it.",
        "why_not_fixed": "Not in the campaign SPEC; found here.",
        "flipped_by": "S4",
        "cells": [
            ("parse.group_i._scan_one_spec", "edge",
             ".shipwright/planning/01-live/spec.md"),
        ],
        "found_by": "iterate-2026-07-18-requirements-golden-corpus",
    },
}

# Bugs the campaign SPEC already named. The rest were found building this.
SPEC_NAMED = ("FV-1", "FV-2")


def as_json_block() -> dict:
    """The reader-facing copy embedded into golden.json."""
    return {
        "_read_me": (
            "These cells are WRONG ON PURPOSE. Do not correct them -- they are "
            "the baseline campaign steps S2-S6 are measured against. Full "
            "rationale: integration-tests/requirements_corpus/frozen_bugs.py"
        ),
        "bugs": {
            bug_id: {
                "what": info["what"],
                "flipped_by": info["flipped_by"],
                "cells": [list(c) for c in info["cells"]],
            }
            for bug_id, info in FROZEN_BUGS.items()
        },
    }
