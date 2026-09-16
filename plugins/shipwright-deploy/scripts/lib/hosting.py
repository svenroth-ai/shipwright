"""Shared hosting-client access: lazy import + error classification.

Both ``rollback.py`` and ``release.py`` need to (a) construct the Jelastic
client without binding ``get_client`` at import time — a test fixture that
installs a fake ``jelastic_client`` module into ``sys.modules`` only takes
effect on a caller that imports it at CALL time, never on a name already
bound when the module was first loaded — and (b) classify exactly which
failures mean "the host said no" rather than a bug in this code. One
implementation, not two independently-maintained copies that could drift
(code review, iterate-2026-09-16-deploy-ac02-ac05-coded-gates).
"""

from __future__ import annotations

import urllib.error

from rollback_report import HostingError

__all__ = ["client", "hosting_errors"]


def client():
    from jelastic_client import get_client

    return get_client()


def hosting_errors() -> tuple[type[BaseException], ...]:
    """Exactly the failures that mean "the host said no", never a local bug.

    ``URLError`` is included because a client that does not wrap transport
    failures would otherwise escape the read-back downgrade and produce no
    report at all. Programming errors (TypeError, KeyError, …) still propagate.
    """
    errors: list[type[BaseException]] = [HostingError, urllib.error.URLError]
    try:
        from jelastic_client import JelasticError
    except ImportError:
        pass
    else:
        if isinstance(JelasticError, type) and issubclass(JelasticError, BaseException):
            errors.append(JelasticError)
    return tuple(errors)
