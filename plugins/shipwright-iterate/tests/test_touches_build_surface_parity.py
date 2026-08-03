"""Cross-surface parity for `touches_build`: one flag, one matching rule.

`touches_build` is raised by two independent surfaces:

* the **diff-driven** detector `touches_build_files()`, which matches an exact
  basename (plus a small glob family) and therefore already refuses
  `my-package.json` and `package.json.bak`;
* the **message-keyword** surface `detect_risk_flags()`, which matches the
  `RISK_TAXONOMY["touches_build"]["patterns"]` regexes against the prompt — and
  is the one that actually fires at SKILL.md Step E.

They must agree on *what counts as naming a build input*. They did not: the
token guards were added to the Python patterns by
iterate-2026-07-31-it5-classification-calibration and the pre-existing JS
patterns — which never carried any guard — were not retrofitted, so all 21 JS
entries in `TOUCHES_BUILD_FILE_PATTERNS` disagreed across the two surfaces.

The tests below are keyed on `TOUCHES_BUILD_FILE_PATTERNS`, the detector's own
SSoT tuple, so a build input added to the detector tomorrow is held to the same
parity without anyone remembering to extend a literal list here. The literal
lists that do appear are the ones a derived test cannot supply: a removal from
the tuple would silently shrink every derived test's parameter set, so the
named cases pin the specific regressions this change fixes.

"fires" throughout this module means "raises `touches_build`". Other flags
match the same strings, so a message proven here not to raise `touches_build`
may still raise something else — see
`test_touches_build_guard_construction.py`, which pins that residue along with
the deliberate case asymmetry.

**Division of labour**, since no one file owns all of `touches_build`:

* `test_classify_complexity_perf.py` — the detector's own behaviour, and the
  message surface for the Python half;
* `test_touches_build_python_inputs_sync.py` — drift between the detector and
  the two documents that promise its trigger paths (SKILL.md, docs/guide.md);
* `test_touches_build_guard_construction.py` — how the guard is built, and the
  limits this change declares;
* this file — agreement **between the two surfaces**, for every entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from classify_complexity import (  # noqa: E402
    TOUCHES_BUILD_BASENAME_GLOBS,
    TOUCHES_BUILD_FILE_PATTERNS,
    detect_risk_flags,
    touches_build_files,
)


def _fires_from_message(text: str) -> bool:
    return "touches_build" in [f["flag"] for f in detect_risk_flags(text)]


# A concrete filename for every glob family, so the glob half joins the
# derived parity tests below instead of being exempt from them.
_GLOB_INSTANCES = tuple(g.replace("*", "-dev") for g in TOUCHES_BUILD_BASENAME_GLOBS)
ALL_BUILD_INPUTS = TOUCHES_BUILD_FILE_PATTERNS + _GLOB_INSTANCES


@pytest.mark.parametrize("fill", [
    # Inside the old `[\w.-]` alphabet…
    "-dev", "_prod", ".dev", "2",
    # …and outside it. `fnmatch`'s `*` accepts any character, so these ARE
    # glob-family members on the diff surface. The message pattern used to
    # stop at `[\w.-]`, so each was a diff-fires / message-silent false
    # negative — the run's own defect class, one alphabet over (external
    # review, openai, `revise`).
    "#", "+extra", "@dev", "~1",
])
def test_the_glob_family_accepts_the_same_alphabet_on_both_surfaces(fill):
    """A glob family is only "covered" if both surfaces accept the same names.

    The derived tests above instantiate `requirements*.txt` with exactly one
    fill, so they cannot see an alphabet mismatch: every probe they build
    happens to be inside the narrower class. This varies the fill instead —
    which is the only thing that distinguishes "the family is covered" from
    "one member of the family is covered".
    """
    name = f"requirements{fill}.txt"
    assert touches_build_files([f"deploy/{name}"]) is True
    assert _fires_from_message(f"pin the transitive dep in {name}")


def test_glob_instances_are_literal_filenames():
    """Guards the derived parameter set above.

    `requirements*.txt` → `requirements-dev.txt`. If a future glob used `?` or
    `[seq]`, the substitution would leave a wildcard in the "filename" and every
    parity test below would silently probe a string no diff ever contains —
    fnmatch would match it against itself and the negatives would pass for the
    wrong reason. Same guard as `test_all_documented_globs_are_detected`.
    """
    for instance in _GLOB_INSTANCES:
        assert not set(instance) & set("*?["), (
            f"{instance!r} still holds an fnmatch metacharacter; this file's "
            f"derived tests cannot instantiate that glob shape"
        )


# ── Positive parity: every build input the detector knows is also a keyword ──

@pytest.mark.parametrize("name", ALL_BUILD_INPUTS)
def test_every_detector_entry_also_fires_from_a_message(name):
    """Diff-driven ⊆ message-keyword.

    Step E reads only the message surface, so a build input present in the
    tuple but absent from the patterns is invisible where classification
    actually happens — that was trg-496e63a7 for the whole Python half.
    """
    assert touches_build_files([f"some/path/{name}"]) is True
    assert _fires_from_message(f"bump the pinned dep in {name}"), (
        f"{name} is detected from a diff but not from a message; "
        f"detect_risk_flags is the surface that fires at SKILL.md Step E"
    )


# ── Negative parity: a longer token containing a build input is not one ──────
#
# These mirror `test_touches_build_files_does_not_match_partial_basename` and
# `test_requirements_glob_does_not_over_match` on the message surface. The diff
# assertion in each is not decoration: it is what makes this a *parity* test
# rather than two independent claims, and it fails if a future widening of the
# detector ever makes the prefixed/suffixed form legitimate.

@pytest.mark.parametrize("name", ALL_BUILD_INPUTS)
def test_a_prefixed_build_input_fires_on_neither_surface(name):
    probe = f"my-{name}"
    assert touches_build_files([probe]) is False
    assert not _fires_from_message(f"restore {probe} from the backup"), (
        f"{probe!r} raises touches_build from a message but not from a diff"
    )


@pytest.mark.parametrize("name", ALL_BUILD_INPUTS)
def test_a_suffixed_build_input_fires_on_neither_surface(name):
    probe = f"{name}.bak"
    assert touches_build_files([probe]) is False
    assert not _fires_from_message(f"delete {probe}"), (
        f"{probe!r} raises touches_build from a message but not from a diff"
    )


@pytest.mark.parametrize("message", [
    # Named cases, JS half — the regressions this change fixes. Held as
    # literals because a removal from TOUCHES_BUILD_FILE_PATTERNS would shrink
    # the derived parameter sets above without failing anything.
    "restore my-package.json from the backup",
    "delete package.json.bak",
    "the vendor-package-lock.json copy is stale",
    "drop yarn.lock.bak",
    "remove pnpm-lock.yaml.bak",
    "archive bun.lockb.old",
    "purge npm-shrinkwrap.json.bak",
    "the my-tsconfig.json override",
    "remove tsconfig.json.orig",
    "rename my-next.config.ts",
    "delete next.config.ts.bak",
    "my-vite.config.js is a fixture",
    "tailwind.config.js.bak leftovers",
    "webpack.config.js.orig leftovers",
    "rollup.config.js.bak leftovers",
])
def test_named_js_partial_tokens_do_not_fire(message):
    assert not _fires_from_message(message)


# ── The guard must not eat ordinary sentence punctuation ────────────────────

@pytest.mark.parametrize("name", ALL_BUILD_INPUTS)
def test_a_build_input_ending_a_sentence_still_fires(name):
    """A trailing period is punctuation, not a further extension.

    The first guard shape shipped (`(?![\\w.-])`) rejected any following `.`,
    so `add a dependency to pyproject.toml.` raised nothing — a false NEGATIVE
    on a risk gate, the unsafe direction, on the single most ordinary way to
    write a sentence. Extending that shape to `package.json` would have spread
    it to the most common build file there is, so the guard rejects a following
    `.` only when a word character follows it (a further extension).
    """
    assert _fires_from_message(f"the change is confined to {name}.")


@pytest.mark.parametrize("name", ALL_BUILD_INPUTS)
def test_a_build_input_in_a_hyphen_compound_still_fires(name):
    """A trailing `-` is prose, exactly as a trailing `.` is.

    `-` is deliberately absent from the trailing guard's character class. The
    two characters pose the identical question — is this part of the filename,
    or of the sentence? — and answering it one way for `.` and the other way
    for `-` is what an intermediate `(?![\\w-])` did. Measured then: `a
    package.json-only bump` raised NOTHING, though the wholly unguarded
    pattern it replaced had fired. A dependency change whose message reads that
    way would have lost the `small` floor, the performance layer, and (per
    `iteration-reviews.md`, "When Self-Review is Sufficient") the full
    code-review trigger — a gate standing down on a real build change.

    The cost, accepted: `package.json-old` fires although it looks like a
    backup name. That is over-firing, which this spec's own tie-breaker prefers
    — a spurious `small` floor against a lost gate. A lookahead cannot tell
    `-old` from `-only`, so there is no third option, only a choice of
    direction.
    """
    assert _fires_from_message(f"a {name}-only bump, nothing else")
    assert _fires_from_message(f"the {name}-vs-lockfile drift")


@pytest.mark.parametrize("message", [
    "we regenerated uv.lock, then re-ran the suite",
    "the dependency lives in `package.json`",
    "see webui/client/package-lock.json for the pin",
    "the pin is in webui\\client\\package.json",
    "bump it in pyproject.toml; nothing else changed",
    "is the version in package.json?",
])
def test_ordinary_prose_around_a_build_input_still_fires(message):
    """Path separators, backticks and trailing punctuation are not part of the
    filename token — the guard must let all of them through."""
    assert _fires_from_message(message)


# ── The config families: an extension is required, on both surfaces ─────────

CONFIG_STEMS = (
    "next.config", "vite.config", "tailwind.config",
    "webpack.config", "rollup.config",
)


@pytest.mark.parametrize("stem", CONFIG_STEMS)
def test_a_bare_config_stem_fires_on_neither_surface(stem):
    """`next\\.config\\.\\w+` requires the extension, and that is the parity
    answer rather than a convenience.

    `TOUCHES_BUILD_FILE_PATTERNS` holds only extensioned literals
    (`next.config.js|ts|mjs|cjs`), so `touches_build_files(["next.config"])` is
    False. Writing the families `next\\.config(\\.\\w+)?` would make five bare
    stems fire from a message with no diff-surface counterpart — the exact
    disagreement this module exists to close.
    """
    assert touches_build_files([stem]) is False
    assert not _fires_from_message(f"edit {stem} to enable standalone output")


@pytest.mark.parametrize("stem", CONFIG_STEMS)
def test_an_extensioned_config_file_fires_on_both_surfaces(stem):
    """The families must still fire on what they exist for — on BOTH surfaces.

    `CONFIG_STEMS` is a literal list, so unlike the tuple-derived tests above it
    does not shrink when an entry leaves `TOUCHES_BUILD_FILE_PATTERNS`. That is
    the point of holding it literally — but only if it guards both halves.
    Asserting the message surface alone would let `vite.config.ts` be deleted
    from the tuple with nothing here failing, while the message surface kept
    firing: the disagreement class this module exists to close, arriving
    through its own blind spot.
    """
    assert touches_build_files([f"{stem}.ts"]) is True
    assert _fires_from_message(f"tweak {stem}.ts to enable standalone output")
    assert _fires_from_message(f"the change is confined to {stem}.ts.")


@pytest.mark.parametrize("stem", CONFIG_STEMS)
def test_a_config_stem_is_not_matched_inside_a_longer_word(stem):
    """`next.configuration` is not `next.config.*`, and `my-next.config.ts`
    is not `next.config.ts`.

    The two assertions are refused by different things, and only the second is
    specific to this sub-pattern's shape: `next.configuration` is stopped by
    the trailing guard, which the optional-extension draft also had, so that
    assertion alone would not have caught it. The `my-` case is stopped by the
    leading guard. Kept together because they are the two ways a stem gets
    read as part of a longer token, but neither pins the required `\\.` —
    `test_a_bare_config_stem_fires_on_neither_surface` is what does that.
    """
    assert not _fires_from_message(f"the {stem}uration helper is unrelated")
    assert not _fires_from_message(f"rename my-{stem}.ts")
