# Round-Trip Tests Reference

How to write tests that catch the producer/consumer drift bugs that
unit tests of either side miss in isolation.

> **Why this doc exists.** The 2026-05-03 env-iterate
> (`adopt-env-local-scaffold`) shipped two latent bugs (BOM stripping,
> inline-comment stripping) despite 47 unit tests, two Gemini reviews,
> and one OpenAI review. Each side's tests passed because each side was
> probed against a stub representation of the format — not against the
> file the OTHER side would write or read. The fix was an empirical
> producer→file-on-disk→consumer round-trip probe, which surfaced both
> bugs in one assertion.
>
> This doc encodes that pattern. It is referenced from:
>
> - `SKILL.md` Path A Step 6 (Build TDD), under "Boundary Probe"
> - `references/iteration-reviews.md` Self-Review Item 7
> - `references/boundary-probes.md` (probe categories triggered by the
>   `touches_io_boundary` risk flag)

---

## Section 1 — Pattern: producer→file→consumer

### Why this catches what unit tests miss

A "test the producer" suite asserts the producer writes `KEY=value\n`.
A "test the consumer" suite asserts the consumer parses `KEY=value\n`
into `{"KEY": "value"}`. Both pass — but each test fixes its OWN
representation of the format. Drift between the two representations is
invisible until a real file flows producer → disk → consumer.

The producer might write a UTF-8 BOM that the producer-side test never
checks for; the consumer might assume no BOM because the consumer-side
test never feeds one. Round-trip catches this with one assertion:

```
write(producer_output) → file → read(consumer_input) → assert == producer_output
```

### Skeleton pytest example

```python
def test_round_trip_env_file(tmp_path):
    """Producer writes the file the consumer must be able to read back."""
    expected = {
        "KEY": "value",
        "WITH_COMMENT": "real-value",
        "QUOTED": "hello # world",
        "EMPTY": "",
    }

    # Producer side
    file_path = tmp_path / ".env"
    write_env_file(file_path, expected)

    # Round-trip via real file on disk (NOT an in-memory stub)
    actual = parse_env_file(file_path)

    assert actual == expected, (
        f"Round-trip mismatch:\n"
        f"  Wrote:    {expected}\n"
        f"  Read back: {actual}"
    )
```

### Variant: cross-process round-trip

When the producer and consumer live in different processes (e.g.
`/shipwright-iterate` writes a config that `/shipwright-build` reads),
add a subprocess invocation:

```python
def test_round_trip_cross_process(tmp_path):
    file_path = tmp_path / "shipwright_run_config.json"
    expected = {"profile": "next-supabase", "status": "complete"}

    # Producer subprocess
    subprocess.run(
        ["uv", "run", "write_run_config.py",
         "--path", str(file_path),
         "--profile", expected["profile"],
         "--status", expected["status"]],
        check=True,
    )

    # Consumer subprocess
    result = subprocess.run(
        ["uv", "run", "read_run_config.py", "--path", str(file_path)],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == expected
```

---

## Section 2 — Pattern: duplicated-consumer drift protection

### When this applies

When the same parser/serializer logic exists in N places (a known
anti-pattern, but common during refactor windows). The env iterate
shipped with `parse_env` in BOTH `lib/env_loader.py` AND
`tools/validate_env.py` — Sven's BOM fix landed in one but not the
other, which the round-trip test surfaced.

### Skeleton parametrized test

```python
import pytest
from lib.env_loader import parse_env_file as parse_a
from tools.validate_env import parse_env_file as parse_b

@pytest.mark.parametrize("parser", [parse_a, parse_b],
                         ids=["lib.env_loader", "tools.validate_env"])
def test_all_parsers_strip_utf8_bom(parser, tmp_path):
    """Drift protection: every duplicated parser must agree on BOM handling."""
    p = tmp_path / "file.env"
    p.write_bytes(b"\xef\xbb\xbfKEY=value\n")
    result = parser(p)
    assert result == {"KEY": "value"}, (
        f"{parser.__module__} disagrees with the BOM convention"
    )
```

The parametrization is the load-bearing part: both parsers go through
the SAME assertion, so any future divergence (a fix landing in one but
not the other) immediately fails the suite.

### Long-term fix vs short-term protection

Drift-protection tests are a workaround. The real fix is to delete the
duplicated implementation and have one source of truth (e.g. extract
into `shared/scripts/lib/`). Until that refactor lands, the
parametrized test prevents regressions across the duplicates.

---

## Section 3 — When to apply

### Triggers

The Boundary Probe sub-step (which runs the round-trip pattern) is
mandatory when ANY of these fire:

1. `classify_complexity.py` returns `touches_io_boundary` in
   `risk_flags` (keyword detection over the user message).
2. `is_io_boundary_change(changed_files)` returns True (path-match
   detection over the diff — see `IO_BOUNDARY_FILE_PATTERNS`).
3. The change introduces a NEW serialized format that other code in
   the repo will read.

### What to probe

For user-edited formats (env files, YAML/TOML config, JSON state files
operators inspect by hand), run the full 8-probe checklist from
`references/boundary-probes.md` PLUS a producer→file→consumer
round-trip test for the happy-path payload.

For machine-only formats, run the round-trip test for the happy-path
payload only. Operator-input categories (POSIX export, inline comment,
hash-in-quotes) may be skipped with a one-line justification in the
Self-Review block.

### Skip rules

The Boundary Probe is **Safety-enforced** in the SKILL.md Override
Classes table — it can only be skipped with explicit risk
acknowledgment in the iterate ADR (e.g. "format change is internal
representation only, no other code reads it"). Trivial flag-bypass is
not allowed.

### Future enhancement: AST-pair detection

`is_io_boundary_change()` currently uses path-match only. A future
enhancement is AST-level detection: scan the diff for files that contain
both writer-style calls (`json.dump`, `yaml.dump`, `Path.write_text`)
AND a separate file in the same diff containing matching reader-style
calls (`json.load`, `yaml.safe_load`, `Path.read_text`). This catches
the case where producer + consumer live in different .py files but
neither file matches the path patterns. Empirically all known
real-world cases are caught by path-match alone, so the AST work is
deferred until a concrete miss surfaces.
