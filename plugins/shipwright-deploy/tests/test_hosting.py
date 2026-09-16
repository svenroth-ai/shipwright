"""Tests for the shared hosting-client access module (hosting.py).

rollback.py and release.py both delegate their client construction and
error classification here — see hosting.py's own docstring for why this
must stay one implementation, not two.
"""

import sys
import types
import urllib.error

import hosting


def test_hosting_errors_falls_back_gracefully_when_jelastic_error_is_absent(monkeypatch):
    """A ``jelastic_client`` module that never defines ``JelasticError`` (an
    older or minimal stand-in) must not crash classification — it just
    means one fewer error type is recognised as "the host said no".
    """
    fake = types.ModuleType("jelastic_client")
    fake.get_client = lambda: None
    monkeypatch.setitem(sys.modules, "jelastic_client", fake)

    errors = hosting.hosting_errors()

    assert errors == (hosting.HostingError, urllib.error.URLError)


def test_hosting_errors_includes_jelastic_error_when_present(monkeypatch):
    class _FakeJelasticError(Exception):
        pass

    fake = types.ModuleType("jelastic_client")
    fake.get_client = lambda: None
    fake.JelasticError = _FakeJelasticError
    monkeypatch.setitem(sys.modules, "jelastic_client", fake)

    errors = hosting.hosting_errors()

    assert _FakeJelasticError in errors
