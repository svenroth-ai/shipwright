"""atomic-frs U1: can an FR still be split? Clusters by bound tests, touched files and wording; the count never decides."""

from __future__ import annotations

import pytest

from pathlib import Path

from lib.fr_cluster_evidence import collect_evidence
from lib.fr_clusters import VERDICT_NO, VERDICT_NONE, VERDICT_PARTIAL, VERDICT_YES, cluster_fr, cluster_frs
from tools.fr_cluster_report import build_report, render

TWO_CAPABILITIES = """### FR-01.01 - Reports and reminders

- (E) [AC01] Given a finished month, when the owner exports the ledger report, then a PDF file with every booking is produced.
- (E) [AC02] Given a ledger report export, when a booking is missing a category, then the export lists it as uncategorised.
- (E) [AC03] Given a ledger report export, when the month has no bookings, then the export says the month is empty.
- (E) [AC04] Given an overdue invoice, when the reminder mail is sent, then the customer receives one reminder message.
- (E) [AC05] Given a reminder mail was sent, when the customer already paid, then no further reminder message is sent.
- (E) [AC06] Given a reminder mail, when the customer address bounces, then the reminder is marked undelivered.
"""
_WORDS = ["balance", "currency", "account", "booking", "statement", "period", "audit", "invoice", "payment", "refund", "deposit", "interest"]
LARGE_ONE = "### FR-01.02 - Ledger postings\n\n" + "".join(
    f"- (E) [AC{i:02d}] Given the {_WORDS[i - 1]} posting rule number {i}, when the ledger posts an entry, then the ledger stays consistent.\n"
    for i in range(1, 13))


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    _write(tmp_path, ".shipwright/planning/01-core/spec.md", TWO_CAPABILITIES + "\n" + LARGE_ONE)
    _write(tmp_path, "src/exporter.py", "def export(): ...\n")
    _write(tmp_path, "src/mailer.py", "def send(): ...\n")
    _write(tmp_path, "src/ledger.py", "def post(): ...\n")
    _write(tmp_path, "tests/test_export.py",
           "from src.exporter import export\n\n"
           '@pytest.mark.covers("FR-01.01/AC01")\ndef test_pdf():\n    pass\n\n'
           'def test_uncategorised():\n    # FR-01.01.AC02\n    pass\n\n'
           'def test_empty_month():\n    # FR-01.01.AC03\n    pass\n')
    _write(tmp_path, "tests/test_mail.py",
           "from src.mailer import send\n\n"
           '@pytest.mark.covers("FR-01.01/AC04")\ndef test_reminder():\n    pass\n\n'
           '@pytest.mark.covers("FR-01.01/AC05")\ndef test_no_second():\n    pass\n\n'
           '@pytest.mark.covers("FR-01.01/AC06")\ndef test_bounce():\n    pass\n')
    # the large FR: twelve criteria over three test files that all touch the ledger module
    for n, group in enumerate((range(1, 5), range(5, 9), range(9, 13))):
        body = "from src.ledger import post\n\n" + "".join(
            f'@pytest.mark.covers("FR-01.02/AC{i:02d}")\ndef test_rule_{i}():\n    pass\n\n' for i in group)
        _write(tmp_path, f"tests/test_ledger_{n}.py", body)
    return tmp_path


@pytest.mark.covers("FR-01.10")
def test_seeded_two_capability_fr_with_few_criteria_is_flagged_and_large_single_capability_fr_is_left_alone(tmp_path):
    report = {r["fr"]: r for r in build_report(_project(tmp_path))}
    small, large = report["FR-01.01"], report["FR-01.02"]
    assert small["ac_count"] == 6 and small["verdict"] == VERDICT_YES
    assert [c["acs"] for c in small["clusters"]] == [[f"FR-01.01.AC0{i}" for i in (1, 2, 3)], [f"FR-01.01.AC0{i}" for i in (4, 5, 6)]]
    assert "src/exporter.py" in small["clusters"][0]["files"] and "src/mailer.py" in small["clusters"][1]["files"]
    assert large["ac_count"] == 12 and large["verdict"] == VERDICT_NO and len(large["clusters"]) == 1


@pytest.mark.covers("FR-01.10")
def test_worklist_puts_splittable_first_and_count_only_sorts(tmp_path):
    order = [r["fr"] for r in build_report(_project(tmp_path))]
    assert order == ["FR-01.01", "FR-01.02"]  # the 6-criteria FR outranks the 12-criteria FR: the count is not the rule


@pytest.mark.covers("FR-01.10")
def test_thin_evidence_says_no_evidence_never_a_guess():
    acs = {f"FR-01.03.AC{i:02d}": f"Given thing {i}, when it runs, then something specific{i} happens" for i in range(1, 9)}
    one_test = {"FR-01.03.AC01": {"tests/t.py::test_a"}}
    r = cluster_fr("FR-01.03", acs, one_test, {})
    assert r["verdict"] == VERDICT_NONE and r["evidenced"] == 1 and r["clusters"] == []
    assert cluster_fr("FR-01.03", acs)["verdict"] == VERDICT_NONE


@pytest.mark.covers("FR-01.10")
def test_wording_alone_never_creates_a_split():
    acs = {"FR-01.04.AC01": "alpha beta gamma delta epsilon", "FR-01.04.AC02": "zeta theta kappa lambda sigma"}
    assert cluster_fr("FR-01.04", acs)["verdict"] == VERDICT_NONE


@pytest.mark.covers("FR-01.10")
def test_shared_wording_joins_two_otherwise_separate_groups():
    acs = {f"FR-01.05.AC0{i}": f"ledger export booking statement period report{i}" for i in (1, 2, 3)}
    tests = {f"FR-01.05.AC0{i}": {f"tests/{i}.py::t"} for i in (1, 2, 3)}
    r = cluster_fr("FR-01.05", acs, tests, {})
    assert r["verdict"] == VERDICT_NO and r["clusters"][0]["joined_by"] == ["shared wording"]


@pytest.mark.covers("FR-01.10")
def test_repo_wide_utility_does_not_join_unrelated_groups():
    acs, tests, files = {}, {}, {}
    for fr in range(1, 6):  # five FRs, each with two triples of criteria; every test imports the same utility module
        for ac in range(1, 7):
            a = f"FR-02.0{fr}.AC0{ac}"
            acs[a], tests[a], files[a] = f"unique{fr}{ac} wording", {f"tests/t{fr}{(ac + 2) // 3}.py::t"}, {"lib/util.py"}
    assert all(r["verdict"] == VERDICT_YES for r in cluster_frs(acs, tests, files))
    one = {k: v for k, v in acs.items() if k.startswith("FR-02.01")}
    assert cluster_frs(one, tests, {k: v for k, v in files.items() if k in one})[0]["verdict"] == VERDICT_NO  # no hub: the shared file joins


@pytest.mark.covers("FR-01.10")
def test_unbound_criterion_attaches_by_wording_else_is_unassigned():
    acs = {"FR-01.06.AC01": "exporter writes pdf file", "FR-01.06.AC02": "exporter pdf layout", "FR-01.06.AC03": "exporter pdf margin",
           "FR-01.06.AC04": "mailer sends reminder", "FR-01.06.AC05": "mailer reminder schedule", "FR-01.06.AC06": "mailer reminder retry",
           "FR-01.06.AC07": "pdf file exporter lists categories", "FR-01.06.AC08": "completely different topic"}
    tests = {f"FR-01.06.AC0{i}": {f"t/{'a' if i < 4 else 'b'}.py::x{i}"} for i in range(1, 7)}
    r = cluster_fr("FR-01.06", acs, tests, {})
    assert r["verdict"] == VERDICT_YES
    assert "FR-01.06.AC07" in r["clusters"][0]["acs"] and r["unassigned"] == ["FR-01.06.AC08"]


def _groups(n_groups, size=3, n_unbound=0, singles=0):
    """``n_groups`` groups of ``size`` criteria (each group shares one test file), plus loose singles and unbound criteria."""
    acs, tests, i = {}, {}, 0
    for g in range(n_groups):
        for k in range(size):
            i += 1
            a = f"FR-03.01.AC{i:02d}"
            acs[a], tests[a] = f"group{g} thing{k}", {f"t/g{g}.py::t{k}"}
    for k in range(singles):
        i += 1
        a = f"FR-03.01.AC{i:02d}"
        acs[a], tests[a] = f"lonely{k} item", {f"t/s{k}.py::t"}
    for k in range(n_unbound):
        i += 1
        acs[f"FR-03.01.AC{i:02d}"] = f"unbound{k} item"
    return acs, tests


@pytest.mark.covers("FR-01.10")
def test_a_group_needs_at_least_three_criteria_two_threes_split_a_two_and_a_six_do_not():
    assert cluster_fr("FR-03.01", *_groups(2, 3), {})["verdict"] == VERDICT_YES  # [3, 3] splits
    acs = {**_groups(1, 6)[0], **{f"FR-03.01.AC0{i}": f"other{i} item" for i in (7, 8)}}
    tests = {**_groups(1, 6)[1], **{f"FR-03.01.AC0{i}": {"t/other.py::t"} for i in (7, 8)}}
    r = cluster_fr("FR-03.01", acs, tests, {})  # [2, 6]: the two are loose, one group is not a split
    assert r["verdict"] == VERDICT_NO and [len(c["acs"]) for c in r["clusters"]] == [6] and r["loose"] == ["FR-03.01.AC07", "FR-03.01.AC08"]
    assert cluster_fr("FR-03.01", *_groups(2, 2), {})["verdict"] == VERDICT_NO  # [2, 2]: both loose, no group at all


@pytest.mark.covers("FR-01.10")
def test_singletons_are_loose_never_groups():
    r = cluster_fr("FR-03.01", *_groups(2, 3, singles=3), {})
    assert r["verdict"] == VERDICT_YES and len(r["clusters"]) == 2  # only the two triples count
    assert r["loose"] == ["FR-03.01.AC07", "FR-03.01.AC08", "FR-03.01.AC09"]
    r = cluster_fr("FR-03.01", *_groups(1, 3, singles=5), {})  # one real group and a pile of loose criteria is NOT a split
    assert r["verdict"] == VERDICT_NO and len(r["clusters"]) == 1 and len(r["loose"]) == 5
    assert cluster_fr("FR-03.01", *_groups(0, singles=8), {})["verdict"] == VERDICT_NO


@pytest.mark.covers("FR-01.10")
def test_a_split_needs_at_least_half_of_the_criteria_bound_to_tests():
    r = cluster_fr("FR-03.01", *_groups(2, 3, n_unbound=8), {})  # 6 of 14 bound: partial evidence, no verdict
    assert r["verdict"] == VERDICT_PARTIAL and "6 of 14" in r["reason"]
    assert cluster_fr("FR-03.01", *_groups(2, 3, n_unbound=6), {})["verdict"] == VERDICT_YES  # 6 of 12 = half: enough


@pytest.mark.covers("FR-01.10")
def test_evidence_reads_marker_above_test_and_inline_reference_and_ignores_fr_level_tags(tmp_path):
    _write(tmp_path, "src/a.py", "")
    _write(tmp_path, "tests/test_x.py",
           'from src.a import *\n@pytest.mark.covers("FR-01.01/AC07")\ndef test_one():\n    pass\n'
           'def test_two():\n    assert 1  # FR-01.01.AC08\n@pytest.mark.covers("FR-01.01")\ndef test_three():\n    pass\n')
    tests, files = collect_evidence(tmp_path)
    assert tests == {"FR-01.01.AC07": {"tests/test_x.py::test_one"}, "FR-01.01.AC08": {"tests/test_x.py::test_two"}}
    assert files["FR-01.01.AC07"] == {"src/a.py"}


@pytest.mark.covers("FR-01.10")
def test_ts_tests_resolve_relative_imports(tmp_path):
    _write(tmp_path, "src/board.ts", "export const a = 1\n")
    _write(tmp_path, "src/board.test.ts", "import { a } from './board'\n// @covers FR-03.01/AC01\nit('shows the board', () => {})\n")
    tests, files = collect_evidence(tmp_path)
    assert tests["FR-03.01.AC01"] == {"src/board.test.ts::shows the board"} and files["FR-03.01.AC01"] == {"src/board.ts"}


@pytest.mark.covers("FR-01.10")
def test_fr_option_prints_only_that_requirement(tmp_path, capsys):
    import json
    from tools import fr_cluster_report as cli
    root = _project(tmp_path)
    assert cli.main(["--project-root", str(root), "--fr", "FR-01.01", "--json"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["fr"] == "FR-01.01" and entry["verdict"] == VERDICT_YES and len(entry["clusters"]) == 2
    assert cli.main(["--project-root", str(root), "--fr", "FR-09.99"]) == 2  # unknown id: non-zero, never an empty "clean"
    assert "not in the catalog" in capsys.readouterr().out


@pytest.mark.covers("FR-01.10")
def test_render_names_groups_and_next_step(tmp_path):
    text = render(build_report(_project(tmp_path)), only_splittable=True)
    assert "FR-01.01" in text and "group 2:" in text and "FR-01.02" not in text and "operator confirms" in text


@pytest.mark.covers("FR-01.10")
def test_unparsed_catalog_is_said_to_be_unreadable_not_zero_splittable(tmp_path, capsys):
    from tools import fr_cluster_report as cli
    _write(tmp_path, ".shipwright/planning/01-core/spec.md", "Prose with no requirement this tool can parse.\n")
    assert cli.main(["--project-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "could not read the catalog" in out and "0 of 0" not in out
    assert cli.main(["--project-root", str(tmp_path / "nowhere"), "--json"]) == 0  # no spec.md at all: same answer, as JSON
    assert '"unparsed": true' in capsys.readouterr().out


@pytest.mark.covers("FR-01.10")
def test_ids_inside_string_literals_and_docstrings_are_not_coverage(tmp_path):
    _write(tmp_path, "tests/test_fixture.py",
           'SPEC = "FR-04.01.AC01 is only fixture data"\n\n'
           'def test_writes_fixture():\n    """Mentions FR-04.01.AC02 in prose."""\n    body = "- [AC03] FR-04.01.AC03"\n'
           '    # FR-04.01.AC04 (a real comment inside the test)\n    assert body\n\n'
           '@pytest.mark.covers("FR-04.01/AC05")\ndef test_decorated():\n    pass\n')
    tests, _ = collect_evidence(tmp_path)
    assert sorted(tests) == ["FR-04.01.AC04", "FR-04.01.AC05"]
    assert tests["FR-04.01.AC04"] == {"tests/test_fixture.py::test_writes_fixture"}
