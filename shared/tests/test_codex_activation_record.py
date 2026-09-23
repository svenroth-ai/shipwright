"""Tests for shared/scripts/lib/codex_activation_record.py (R2 — AC1a).

``mint()``/``read()``/``consume()`` implement the exclusive-create-once /
exclusive-consume-once state machine behind a Codex-driven iterate's
activation record. Fail-open is a hard, pre-decided contract (R0's ADR):
absent, corrupt, cwd-mismatched, or expired records are all unconditionally
"no record". The only thing enforced strictly is exclusivity: mint never
overwrites, consume never lets a second caller claim an already-consumed
record. See the module's own docstring for storage layout and fields.
"""

from __future__ import annotations

from pathlib import Path


def test_mint_creates_armed_record(tmp_path):
    from lib.codex_activation_record import mint

    record = mint(
        tmp_path, session_id="s1", turn_id="t1", cwd="/proj",
        armed=True, skill_id="shipwright-iterate:iterate", args={"run_id": "r2"},
    )

    assert record is not None
    assert record.armed is True
    assert record.session_id == "s1"
    assert record.turn_id == "t1"
    assert record.cwd == "/proj"
    assert record.skill_id == "shipwright-iterate:iterate"
    assert record.args == {"run_id": "r2"}
    assert record.schema_version == 1
    assert record.generation  # non-empty opaque token


def test_mint_creates_unarmed_record_with_no_skill_id_or_args(tmp_path):
    from lib.codex_activation_record import mint

    record = mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=False)

    assert record is not None
    assert record.armed is False
    assert record.skill_id is None
    assert record.args is None


def test_args_default_to_empty_dict_when_armed_without_args(tmp_path):
    from lib.codex_activation_record import mint

    record = mint(
        tmp_path, session_id="s1", turn_id="t1", cwd="/proj",
        armed=True, skill_id="x",
    )

    assert record.args == {}


def test_mint_second_call_does_not_overwrite(tmp_path):
    from lib.codex_activation_record import mint

    first = mint(
        tmp_path, session_id="s1", turn_id="t1", cwd="/proj",
        armed=True, skill_id="first", args={},
    )
    second = mint(
        tmp_path, session_id="s1", turn_id="t2", cwd="/proj",
        armed=True, skill_id="second", args={},
    )

    assert first is not None
    assert second is None

    from lib.codex_activation_record import read
    on_disk = read(tmp_path, "s1", cwd="/proj")
    assert on_disk.skill_id == "first"


def test_mint_empty_session_id_returns_none(tmp_path):
    from lib.codex_activation_record import mint

    assert mint(tmp_path, session_id="", turn_id="t1", cwd="/proj", armed=True, skill_id="x") is None
    assert mint(tmp_path, session_id="   ", turn_id="t1", cwd="/proj", armed=True, skill_id="x") is None


def test_read_returns_minted_record(tmp_path):
    from lib.codex_activation_record import mint, read

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x", args={"a": 1})

    record = read(tmp_path, "s1", cwd="/proj")

    assert record is not None
    assert record.skill_id == "x"
    assert record.args == {"a": 1}


def test_read_returns_none_when_absent(tmp_path):
    from lib.codex_activation_record import read

    assert read(tmp_path, "never-minted", cwd="/proj") is None


def test_read_returns_none_on_cwd_mismatch(tmp_path):
    from lib.codex_activation_record import mint, read

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj-a", armed=True, skill_id="x")

    assert read(tmp_path, "s1", cwd="/proj-b") is None


def test_read_returns_none_when_expired(tmp_path):
    from lib.codex_activation_record import mint, read

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x",
         ttl_seconds=10.0, now=1000.0)

    assert read(tmp_path, "s1", cwd="/proj", now=1011.0) is None


def test_expiry_boundary_now_equal_expiry_is_expired(tmp_path):
    # now >= expiry, not now > expiry -- an exact-boundary tick counts as expired,
    # not the last still-valid instant, so the window can never be off-by-one open.
    from lib.codex_activation_record import mint, read

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x",
         ttl_seconds=10.0, now=1000.0)

    assert read(tmp_path, "s1", cwd="/proj", now=1010.0) is None
    assert read(tmp_path, "s1", cwd="/proj", now=1009.999) is not None


def test_read_returns_none_on_corrupt_json(tmp_path):
    from lib.codex_activation_record import _record_path, read

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json at all {{{", encoding="utf-8")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_read_returns_none_on_non_dict_json(tmp_path):
    from lib.codex_activation_record import _record_path, read

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_read_returns_none_on_schema_version_mismatch(tmp_path):
    from lib.codex_activation_record import _record_path, read
    import json as _json

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps({
        "schema_version": 999, "session_id": "s1", "turn_id": "t1", "cwd": "/proj",
        "generation": "abc", "armed": True, "skill_id": "x", "args": {},
        "minted_at": 0.0, "expiry": 9e9,
    }), encoding="utf-8")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_read_returns_none_on_invalid_utf8_bytes(tmp_path):
    from lib.codex_activation_record import _record_path, read

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe\x00\x01invalid-utf8-not-json")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_mint_after_expiry_does_not_remint(tmp_path):
    from lib.codex_activation_record import mint, read

    first = mint(
        tmp_path, session_id="s1", turn_id="t1", cwd="/proj",
        armed=True, skill_id="first", args={}, ttl_seconds=10.0, now=1000.0,
    )
    assert first is not None

    # Same session_id, called again well past the first record's expiry --
    # mint is exclusive-create-only and never expiry-aware; there is no
    # "second first prompt" to remint from (first-prompt-embedded framing,
    # iterate-spec.md's Affected Boundaries row).
    second = mint(
        tmp_path, session_id="s1", turn_id="t2", cwd="/proj",
        armed=True, skill_id="second", args={}, now=2000.0,
    )
    assert second is None

    # And read() at this same later time independently reports expired --
    # NOT because mint quietly re-armed anything, but because the ORIGINAL
    # (still on disk, unchanged) record's own expiry has passed.
    assert read(tmp_path, "s1", cwd="/proj", now=2000.0) is None


def test_cwd_normalization_treats_worktree_and_main_root_as_same(tmp_path, monkeypatch):
    import lib.codex_activation_record as car

    # Simulate mint() seeing a worktree path and read() seeing the main repo
    # root -- both must resolve to the same git identity via git_base
    # (mini-plan Step 4), not compare literal path spelling.
    monkeypatch.setattr(car.git_base, "main_repo_root", lambda p: Path("/canonical/repo"))

    minted = car.mint(
        tmp_path, session_id="s1", turn_id="t1", cwd="/worktrees/foo",
        armed=True, skill_id="x",
    )
    assert minted is not None
    assert minted.cwd == "/canonical/repo" or minted.cwd == str(Path("/canonical/repo"))

    assert car.read(tmp_path, "s1", cwd="/some/other/spelling") is not None


def test_cwd_normalization_falls_back_to_literal_when_not_a_git_repo(tmp_path):
    # tmp_path is not a git repository, so normalize_cwd()'s git call fails
    # and both mint()/read() fall back to comparing the raw cwd string --
    # this is the behavior every other test in this file already relies on
    # implicitly; asserted explicitly here since it's the fallback path the
    # cwd-normalization fix must never break.
    from lib.codex_activation_record import mint, read

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj-a", armed=True, skill_id="x")

    assert read(tmp_path, "s1", cwd="/proj-a") is not None
    assert read(tmp_path, "s1", cwd="/proj-b") is None


def test_mint_second_call_skips_normalize_cwd_entirely(tmp_path, monkeypatch):
    # doubt-review, medium: a repeat mint() must exit on exists() before
    # ever calling normalize_cwd() -- asserted by making that call raise.
    import lib.codex_activation_record as car

    car.mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x")

    def _boom(_cwd):
        raise AssertionError("normalize_cwd() must not run on a repeat mint()")

    monkeypatch.setattr(car, "normalize_cwd", _boom)
    assert car.mint(tmp_path, session_id="s1", turn_id="t2", cwd="/proj", armed=True) is None


def test_consume_second_call_skips_read_and_normalize_cwd_entirely(tmp_path, monkeypatch):
    # doubt-review, medium: once consumed, every later PreToolUse call's
    # consume() must exit on the .consumed exists() check before read()
    # (and therefore normalize_cwd()) ever runs.
    import lib.codex_activation_record as car

    car.mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x")
    first = car.consume(tmp_path, "s1", cwd="/proj")
    assert first is not None

    def _boom(*_a, **_kw):
        raise AssertionError("read() must not run on an already-consumed session")

    monkeypatch.setattr(car, "read", _boom)
    assert car.consume(tmp_path, "s1", cwd="/proj") is None


def test_purge_expired_records_reaps_stale_pairs_but_keeps_fresh_ones(tmp_path):
    import lib.codex_activation_record as car

    car.mint(
        tmp_path, session_id="stale", turn_id="t1", cwd="/proj",
        armed=True, skill_id="x", ttl_seconds=10.0, now=1000.0,
    )
    car.consume(tmp_path, "stale", cwd="/proj", now=1000.0)
    assert car._record_path(tmp_path, "stale").exists()
    assert car._consumed_path(tmp_path, "stale").exists()

    # "stale" is now expired (expiry 1010 < 2000); mint()'s purge reaps it
    # as a side effect of minting "fresh", which must itself survive.
    car.mint(
        tmp_path, session_id="fresh", turn_id="t1", cwd="/proj",
        armed=True, skill_id="x", ttl_seconds=10_000.0, now=2000.0,
    )

    assert not car._record_path(tmp_path, "stale").exists()
    assert not car._consumed_path(tmp_path, "stale").exists()
    assert car._record_path(tmp_path, "fresh").exists()


def test_purge_expired_records_skips_malformed_json_without_raising(tmp_path):
    import lib.codex_activation_record as car

    record_dir = tmp_path / ".shipwright" / "runtime" / "codex-activation"
    record_dir.mkdir(parents=True)
    (record_dir / "junk.json").write_text("not json", encoding="utf-8")

    car._purge_expired_records(record_dir, now=1_000_000.0)

    assert (record_dir / "junk.json").exists()  # skipped, not deleted

