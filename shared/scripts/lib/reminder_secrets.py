"""The secret check for reminder text — refuses, never stores.

A reminder is plain text that part 2 of the reminders work mails off the machine,
so no secret may reach the store. The check covers EVERY text field, including
``command`` and each link's ``label`` / ``ref``.

Pattern source: :func:`lib.main_health_diagnosis.contains_secret` (the one public
credential-shape set, which has no URL rule) plus the URL-credential rules below.
Defense-in-depth, not a guarantee: it recognises known shapes only.
"""

from __future__ import annotations

import re

from lib.main_health_diagnosis import contains_secret

#: ``scheme://user:pass@host`` — credentials embedded in a URL authority. A token-only
#: userinfo (``https://<token>@host``) is left to ``contains_secret``'s token shapes, so a
#: harmless ``ssh://git@host/repo`` ref is not refused.
_URL_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s/@:?#]+:[^\s/@]+@")
#: A bare ``user:pass@host`` (no scheme) is not matched on purpose: it is
#: indistinguishable from an e-mail address plus a colon in prose.
_URL_SECRET_PARAM = re.compile(
    r"[?&#](?:token|access_token|auth|key|api_key|apikey|secret|password|passwd|sig)=[^\s&#]+",
    re.IGNORECASE,
)

REFUSAL = (
    "looks like it contains a secret (a key, token, password or a URL with "
    "credentials). Reminders are shown and mailed in plain text, so reword it "
    "without the secret, for example name where it is kept instead."
)


def text_has_secret(text: str) -> bool:
    """True when ``text`` carries a known secret shape or URL credentials."""
    if not isinstance(text, str):
        return False
    return bool(
        contains_secret(text)
        or _URL_USERINFO.search(text)
        or _URL_SECRET_PARAM.search(text)
    )


def find_secret_field(fields: dict[str, object]) -> str | None:
    """Return the name of the first text field that carries a secret, else None.

    ``fields`` maps a human field name to its value: a string, a list of
    strings, or a list of link dicts (their ``label`` / ``ref`` are checked and
    named ``links[i].label`` / ``links[i].ref``).
    """
    for name, value in fields.items():
        if isinstance(value, str):
            if text_has_secret(value):
                return name
        elif isinstance(value, list):
            for i, entry in enumerate(value):
                if isinstance(entry, str):
                    if text_has_secret(entry):
                        return f"{name}[{i}]"
                elif isinstance(entry, dict):
                    for sub, sub_value in entry.items():
                        if isinstance(sub_value, str) and text_has_secret(sub_value):
                            return f"{name}[{i}].{sub}"
    return None
