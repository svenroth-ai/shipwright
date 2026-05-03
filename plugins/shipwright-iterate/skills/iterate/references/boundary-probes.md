# Boundary Probes Reference

Canonical edge-case list for the **Boundary Probe** sub-step in
`/shipwright-iterate` Build TDD (Path A Step 6, Path B Step 6, Path C
Step 5). Triggered by the `touches_io_boundary` risk flag.

> **Why this doc exists.** The 2026-05-03 env-iterate (`adopt-env-local-scaffold`)
> shipped two latent producer/consumer bugs that survived 47 unit tests
> AND two external LLM reviews:
>
> 1. `parse_env_file` did not strip trailing `# comment`, so
>    `os.environ["KEY"]` got `'sk-or-real        # description'` instead
>    of `'sk-or-real'`.
> 2. UTF-8 BOM from Notepad-saved files prefixed the first key
>    (`﻿KEY` instead of `KEY`).
>
> Both were caught by an empirical producer→file→consumer round-trip
> probe — not by either side's unit tests. This doc encodes the
> probe categories so future iterates can't ship the same class of bug.

See also: `references/round-trip-tests.md` for the test patterns themselves.

---

## UTF-8 BOM (Byte-Order Mark)

**Rationale.** Files saved by Windows Notepad, some Java/Eclipse exporters,
and a handful of Excel "Save as CSV (UTF-8)" paths get a leading
`\xEF\xBB\xBF` (`﻿`). Most parsers do NOT strip it — the first key
becomes `﻿KEY` and `os.environ["KEY"]` returns `None`.

**Failing-scenario one-liner.** Producer writes UTF-8 text without BOM;
operator opens + saves the file in Notepad; consumer reads the first
key as `﻿KEY` and the lookup misses.

**Recommended pytest pattern.**
```python
def test_parse_strips_utf8_bom(tmp_path):
    p = tmp_path / "file.env"
    p.write_bytes(b"\xef\xbb\xbfKEY=value\n")
    result = parse_env_file(p)
    assert result == {"KEY": "value"}
```

---

## CRLF Line Endings

**Rationale.** Files committed on Windows or edited in cross-platform
tools (PowerShell `Set-Content`, some IDEs) end lines with `\r\n` instead
of `\n`. Naive `line.split("=")` then yields `"value\r"` for every value,
which downstream string compares fail silently.

**Failing-scenario one-liner.** Producer writes `\n`-terminated lines on
Linux CI; consumer on a developer's Windows box reads back values with a
trailing `\r` and `value == "expected"` returns False without surfacing
the carriage return.

**Recommended pytest pattern.**
```python
def test_parse_handles_crlf(tmp_path):
    p = tmp_path / "file.env"
    p.write_bytes(b"KEY=value\r\nOTHER=2\r\n")
    result = parse_env_file(p)
    assert result == {"KEY": "value", "OTHER": "2"}
```

---

## Non-ASCII Values

**Rationale.** API keys, descriptions, and user-facing strings can contain
umlauts (`ä`, `ö`, `ü`), em-dashes (`—`), or non-Latin scripts. A parser
that opens the file with `open(p)` instead of
`open(p, encoding="utf-8")` falls back to the locale default — `cp1252`
on most Windows installs — and either UnicodeDecodeError-crashes or
silently mojibake-corrupts the value.

**Failing-scenario one-liner.** Producer writes `KEY=München` as UTF-8;
consumer opens the file with the locale default and gets `München` or a
crash, not the original string.

**Recommended pytest pattern.**
```python
def test_parse_preserves_non_ascii(tmp_path):
    p = tmp_path / "file.env"
    p.write_text("KEY=München\n", encoding="utf-8")
    result = parse_env_file(p)
    assert result["KEY"] == "München"
```

---

## POSIX `export KEY=value` Prefix

**Rationale.** Operators copy-paste lines from shell sessions or `.bashrc`
fragments into `.env` files. The literal `export ` prefix is part of the
shell syntax, not the env-file format; a strict parser then sets the key
as `export KEY` (with space) and the lookup fails.

**Failing-scenario one-liner.** Operator pastes `export OPENROUTER_KEY=sk-...`
into `.env.local`; parser stores `os.environ["export OPENROUTER_KEY"]`,
and `os.environ.get("OPENROUTER_KEY")` returns None.

**Recommended pytest pattern.**
```python
def test_parse_strips_export_prefix(tmp_path):
    p = tmp_path / "file.env"
    p.write_text("export KEY=value\n", encoding="utf-8")
    result = parse_env_file(p)
    assert result == {"KEY": "value"}
```

---

## Inline `# comment`

**Rationale.** Operators annotate keys inline:
`OPENROUTER_KEY=sk-or-real        # billing acct A`. A parser that
takes the entire `value` substring after `=` includes the trailing
comment + whitespace as part of the key value. This is the exact bug
that shipped on 2026-05-03 in the env iterate.

**Failing-scenario one-liner.** Producer writes `KEY=sk-real    # comment`;
consumer's API call signs requests with `sk-real    # comment` and the
remote rejects every request with HTTP 401.

**Recommended pytest pattern.**
```python
def test_parse_strips_inline_comment(tmp_path):
    p = tmp_path / "file.env"
    p.write_text("KEY=sk-real        # billing acct A\n", encoding="utf-8")
    result = parse_env_file(p)
    assert result == {"KEY": "sk-real"}
```

---

## `#` Without Leading Whitespace Inside a Value

**Rationale.** A heuristic that strips inline comments by splitting on
the first `#` will mangle values that legitimately contain `#`
characters (e.g. `URL=https://example.com/page#anchor`,
`PASSWORD=p@ss#word!`). The fix from the previous probe
(strip `# comment`) must NOT apply if the `#` is inside a value with
no leading whitespace — only `WHITESPACE+#` should signal a comment.

**Failing-scenario one-liner.** Producer writes
`URL=https://example.com/path#section`; over-eager comment stripper
returns `URL=https://example.com/path` and the deep link breaks.

**Recommended pytest pattern.**
```python
def test_parse_keeps_hash_without_leading_whitespace(tmp_path):
    p = tmp_path / "file.env"
    p.write_text("URL=https://example.com/path#section\n", encoding="utf-8")
    result = parse_env_file(p)
    assert result["URL"] == "https://example.com/path#section"
```

---

## Quoted Values Containing `#`

**Rationale.** Once quote handling enters the parser, the `# comment`
stripper must respect quote context: `MSG="hello # world"` is a single
value `hello # world`, not `hello ` with a comment.

**Failing-scenario one-liner.** Producer writes `MSG="hello # world"`;
naive stripper produces `MSG="hello`, leaving an unbalanced quote that
the consumer either errors on or silently passes downstream.

**Recommended pytest pattern.**
```python
def test_parse_keeps_hash_inside_quotes(tmp_path):
    p = tmp_path / "file.env"
    p.write_text('MSG="hello # world"\n', encoding="utf-8")
    result = parse_env_file(p)
    assert result["MSG"] == "hello # world"
```

---

## Empty Values (`KEY=`, `KEY=""`)

**Rationale.** Operators sometimes leave keys deliberately empty
(disabled flags, optional API keys staged for later). A parser that
splits on `=` and indexes `[1]` works for `KEY=value` but should also
handle `KEY=` (no RHS) and `KEY=""` (explicit empty string) without
crashing or treating them as "key absent".

**Failing-scenario one-liner.** Producer writes `OPTIONAL_KEY=`;
consumer's `if "OPTIONAL_KEY" in env:` returns True but
`env["OPTIONAL_KEY"]` IndexErrors or returns the literal `""` —
downstream code paths diverge based on which.

**Recommended pytest pattern.**
```python
def test_parse_handles_empty_values(tmp_path):
    p = tmp_path / "file.env"
    p.write_text('EMPTY=\nQUOTED_EMPTY=""\n', encoding="utf-8")
    result = parse_env_file(p)
    assert result == {"EMPTY": "", "QUOTED_EMPTY": ""}
```

---

## When to apply this list

The Boundary Probe sub-step in Build TDD MUST run all 8 probe
categories above when:

- `classify_complexity.py` returns `touches_io_boundary` in `risk_flags`, OR
- The diff changes any file matching `IO_BOUNDARY_FILE_PATTERNS`
  (detected via `is_io_boundary_change(changed_files)`), OR
- The change introduces a NEW serialized format that any other code
  in the repo will read.

For user-edited formats (env files, YAML config, JSON state files),
ALL 8 categories apply. For machine-only formats (e.g. internal
state.json never opened by hand), categories specific to operator
input — POSIX export prefix, inline `# comment`, quoted values
containing `#` — may be skipped with a one-line justification in the
iterate's Self-Review block.

See `references/round-trip-tests.md` for the producer→file→consumer
test pattern itself.
