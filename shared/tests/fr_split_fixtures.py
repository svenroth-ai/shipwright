"""Shared fixtures for the fr_split tests: a small spec, a throwaway project and a byte snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from lib.fr_split_spec import split_spec


_ACS = {
    1: "Given a plan, when it is saved, then it is stored.",
    2: "Given a plan, when it is loaded, then it is shown.",
    3: "Given a plan, when it is removed, then it is gone.",
    4: "Given a mail, when it is sent, then the customer receives one message.",
    5: "Given a mail, when the address bounces, then the mail is marked undelivered.",
    6: "Given a mail, when the customer paid, then no further message is sent.",
}


def _spec(extra_fr: str = "") -> str:
    rows = "\n".join(f"| FR-01.0{i} | Core | {n} | Must | Does {n.lower()}. | code | unit (inferred) |"
                     for i, n in ((1, "Plans and mail"), (2, "Other thing")))
    bullets = "\n".join(f"- (E) [AC{n:02d}] {t}\n  Second line of {n}." for n, t in _ACS.items())
    return (f"# Spec\n\n## Functional Requirements\n\n| ID | Area | Name | Priority | Description | Basis | Layers |\n|---|---|---|---|---|---|---|\n"
            f"{rows}\n\n## Acceptance Criteria\n\n<a id=\"fr-0101\"></a>\n### FR-01.01 — Plans and mail\n\n{bullets}\n\n"
            f"<a id=\"fr-0102\"></a>\n### FR-01.02 — Other thing\n\n- (E) [AC01] Given x, when y, then z.\n{extra_fr}\n## Provenance\n\nText.\n")


GROUPING = {"source": "FR-01.01", "parts": [{"title": "Mail reminders", "description": "Remind customers by mail.", "acs": [4, 5, 6]}]}


def _cut(text: str | None = None, grouping: dict | None = None):
    return split_spec(text or _spec(), grouping or GROUPING)


MOVES = {"FR-01.01/AC04": "FR-01.03/AC04", "FR-01.01/AC05": "FR-01.03/AC05"}


PY = '''import pytest

FIXTURE = "FR-01.01/AC04 is only fixture data"

@pytest.mark.covers("FR-01.01/AC04", "FR-01.01/AC01")
def test_a():
    # FR-01.01.AC05 explained here
    assert FIXTURE

@pytest.mark.covers("FR-01.01")
def test_bare_fr_level_tag_stays():
    pass
'''


def _project(tmp_path: Path, shared_test: bool = False) -> tuple[Path, Path]:
    def w(rel: str, text: str) -> None:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    w(".shipwright/planning/01-core/spec.md", _spec())
    w("src/plans.py", "def save(): ...\n")
    w("src/mail.py", "def send(): ...\n")
    tags = lambda n: f'@pytest.mark.covers("FR-01.01/AC0{n}")\ndef test_{n}():\n    pass\n\n'  # noqa: E731
    body = "import pytest\nfrom src.plans import save\n\n" + "".join(tags(n) for n in (1, 2, 3))
    w("tests/test_plans.py", body)
    mail = "import pytest\nfrom src.mail import send\n\n" + "".join(tags(n) for n in (4, 5, 6))
    if shared_test:
        mail += '@pytest.mark.covers("FR-01.01/AC04", "FR-01.01/AC01")\ndef test_both():\n    pass\n'
    w("tests/test_mail.py", mail)
    w("shipwright_ac_coverage_baseline.json", '{\n  "schema_version": 1,\n  "unbound": [\n    "FR-01.01/AC05",\n    "FR-01.02/AC01"\n  ]\n}\n')
    cut = tmp_path / "cut.json"
    cut.write_text(json.dumps(GROUPING), encoding="utf-8")
    return tmp_path, cut


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
