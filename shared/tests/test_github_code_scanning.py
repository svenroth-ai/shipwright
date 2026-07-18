"""The thin ``gh`` shell for code scanning — list, dismiss, reopen.

``_run`` is the single seam, so the shell is driven end-to-end offline and
in-process: no network, and the lines still count toward diff coverage (a
subprocess-invoked CLI would contribute none).

The load-bearing property is ``None`` vs ``[]``. A failed fetch must never read
as "every alert cleared", which in this tool means "converged" (ADR-052).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import github_code_scanning as gcs  # noqa: E402


class TestGhShell:
    @pytest.mark.parametrize("slug", ["svenroth-ai/shipwright", "a/b", "o.rg/re-po_1"])
    def test_valid_slugs_pass(self, slug):
        assert gcs.validate_owner_repo(slug) == slug

    @pytest.mark.parametrize("junk", [
        None, 42, "", "noslash", "a/b/c", "../../etc", "a/b?x=1", "-lead/repo",
        "a/b&curl", "o/r ",
    ])
    def test_unresolvable_identity_raises_rather_than_degrading(self, junk):
        """A soft failure here degrades into acting on whatever the working
        directory happens to point at."""
        with pytest.raises(gcs.RepoIdentityError):
            gcs.validate_owner_repo(junk)

    def test_list_alerts_paginates_and_parses(self, monkeypatch):
        seen = {}
        def fake(args):
            seen["args"] = args
            return 0, '[{"number": 1}]'
        monkeypatch.setattr(gcs, "_run", fake)
        assert gcs.list_alerts("a/b", "dismissed") == [{"number": 1}]
        assert "--paginate" in seen["args"]
        assert "state=dismissed" in " ".join(seen["args"])

    @pytest.mark.parametrize("result", [(1, ""), (0, "not json"), (0, '{"a": 1}')])
    def test_failed_or_non_list_fetch_is_none_never_empty(self, monkeypatch, result):
        """``None`` vs ``[]`` is load-bearing (ADR-052): a failed fetch must
        never read as 'every alert cleared', which here means 'converged'."""
        monkeypatch.setattr(gcs, "_run", lambda a: result)
        assert gcs.list_alerts("a/b", "open") is None

    def test_dismiss_sends_state_reason_and_comment(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(gcs, "_run", lambda a: (seen.setdefault("a", a), (0, "ok"))[1])
        ok, _ = gcs.dismiss_alert("a/b", 5, reason="won't fix", comment="because")
        joined = " ".join(seen["a"])
        assert ok and "PATCH" in joined and "state=dismissed" in joined
        assert "dismissed_reason=won't fix" in joined and "a/b/code-scanning/alerts/5" in joined

    def test_reopen_sets_state_open(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(gcs, "_run", lambda a: (seen.setdefault("a", a), (0, ""))[1])
        ok, _ = gcs.reopen_alert("a/b", 9)
        assert ok and "state=open" in " ".join(seen["a"])

    def test_failure_is_reported_not_swallowed(self, monkeypatch):
        monkeypatch.setattr(gcs, "_run", lambda a: (1, "boom"))
        assert gcs.dismiss_alert("a/b", 1, reason="won't fix", comment="c")[0] is False
        assert gcs.reopen_alert("a/b", 1)[0] is False

    def test_subprocess_failure_degrades_to_a_failed_fetch(self, monkeypatch):
        def boom(*_a, **_kw):
            raise OSError("gh missing")
        monkeypatch.setattr(gcs.subprocess, "run", boom)
        assert gcs.list_alerts("a/b", "open") is None

    def test_gh_output_is_decoded_as_utf8_not_the_locale_codec(self, monkeypatch):
        """Regression: `text=True` alone decodes with the LOCALE codec, which on
        a Windows runner is cp1252 and raises on the first non-Latin-1 byte in
        an alert body. It failed closed (correctly) but permanently — the live
        run could never converge on Windows. Caught by running it, not by a
        unit test, so it is pinned here."""
        seen = {}

        class Result:
            returncode = 0
            stdout = "[]"

        monkeypatch.setattr(gcs.subprocess, "run",
                            lambda *a, **kw: (seen.update(kw), Result())[1])
        gcs.list_alerts("a/b", "open")
        assert seen["encoding"] == "utf-8"
        assert seen["errors"] == "replace"
