#!/usr/bin/env python3
"""Brief-intake for shipwright-run (K2c).

The WebUI Intent Wizard (K2) asks four plain-language questions and hands
``/shipwright-run`` a pre-delivered *brief* (file path or inline payload):
description (free text), users (just_me|team|public), persistence
(yes|no|unsure), run_location (local|web). This module parses it, maps the
answers to profile + deploy/env, and reports which interview questions are
still missing — so the terminal interview asks ONLY what the wizard did NOT.

Mapping (concept §2.1/§2.2): persistence=yes -> supabase-nextjs; no/unsure ->
vite-hono (zero-signup local default); run_location web -> deploy target set,
local -> "none"; supabase env questions asked ONLY when supabase AND web.

No brief -> legacy interview unchanged: ``intake(None)`` reports has_brief
False and every brief-answerable question still remaining (AC3). An explicit
but unreadable brief file degrades the same way. CLI: --brief <path|payload>.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Union

# The four wizard answers, in interview order — the ONLY questions a brief can
# pre-answer (autonomy, env vars are handled separately).
BRIEF_QUESTIONS = ["description", "users", "persistence", "run_location"]

# Non-brief question the wizard never sets -> always still asked.
_ALWAYS_ASK = ["autonomy"]

# Non-optional required_env_vars.build from shared/profiles/supabase-nextjs.json
# — the exact names `build` needs, so the prompt sends the right vars.
SUPABASE_ENV_QUESTIONS = [
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
]

# A brief FILE is only read when it has a suffix this module can parse (JSON, or
# `.md`/`.txt` key:value/fenced) and a sane size, so a stray path (e.g.
# `@/etc/passwd`) never slurps an arbitrary file into the prompt.
_BRIEF_SUFFIXES = {".json", ".md", ".txt"}
_MAX_BRIEF_BYTES = 256 * 1024

# Synonym tables: lower-cased/stripped answer text -> canonical value. The
# wizard emits canonical values, but a hand-written or WebUI-variant brief may
# use the human-facing labels ("Customers / public", "Just my machine").
_USERS_SYNONYMS = {
    "just_me": "just_me", "just me": "just_me", "only me": "just_me",
    "me": "just_me", "myself": "just_me", "solo": "just_me",
    "team": "team", "my team": "team", "internal": "team",
    "colleagues": "team", "coworkers": "team",
    "public": "public", "customers": "public", "clients": "public",
    "customers / public": "public", "customers/public": "public",
    "everyone": "public",
}
_PERSISTENCE_SYNONYMS = {
    "yes": "yes", "y": "yes", "true": "yes",
    "no": "no", "n": "no", "false": "no",
    "unsure": "unsure", "not sure": "unsure", "not sure yet": "unsure",
    "maybe": "unsure", "dunno": "unsure", "don't know": "unsure",
    "dont know": "unsure",
}
_RUN_LOCATION_SYNONYMS = {
    "local": "local", "machine": "local", "my machine": "local",
    "just my machine": "local", "my computer": "local", "localhost": "local",
    "web": "web", "cloud": "web", "online": "web", "internet": "web",
    "hosted": "web", "deployed": "web", "on the web": "web",
}

_SYNONYMS = {
    "users": _USERS_SYNONYMS,
    "persistence": _PERSISTENCE_SYNONYMS,
    "run_location": _RUN_LOCATION_SYNONYMS,
}


def _canonical(field: str, value) -> Optional[str]:
    """Map a raw answer value to its canonical token, or None if unknown."""
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    return _SYNONYMS[field].get(key)


def normalize_brief(raw: dict) -> dict:
    """Normalize a raw brief dict to the four canonical fields.

    Unknown/empty coded answers collapse to None. ``description`` is free text
    (empty -> None). A non-dict brief (JSON array/scalar) degrades, not crashes.
    """
    raw = raw if isinstance(raw, dict) else {}
    desc = raw.get("description")
    if desc is not None and not isinstance(desc, str):
        desc = str(desc)  # a non-string description (number/list) -> str, so it
    if isinstance(desc, str) and not desc.strip():  # is never a silent non-str
        desc = None
    return {
        "description": desc,
        "users": _canonical("users", raw.get("users")),
        "persistence": _canonical("persistence", raw.get("persistence")),
        "run_location": _canonical("run_location", raw.get("run_location")),
    }


def map_brief(brief: dict) -> dict:
    """Map a normalized brief to profile/deploy/env + remaining questions."""
    persistence = brief.get("persistence")
    run_location = brief.get("run_location")
    users = brief.get("users")

    # Profile: persistence drives the DB decision; vite-hono is the zero-signup
    # default for "no"/"unsure". Unknown persistence -> cannot fix profile.
    if persistence == "yes":
        profile = "supabase-nextjs"
        profile_reason = "persistence=yes -> real database (supabase-nextjs)"
    elif persistence in ("no", "unsure"):
        profile = "vite-hono"
        profile_reason = (
            "persistence=%s -> local zero-signup default (vite-hono)" % persistence
        )
    else:
        profile = None
        profile_reason = "persistence unknown -> profile still to decide"

    # Deploy target from run-location.
    if run_location == "web":
        deploy_target = "jelastic-dev"
    elif run_location == "local":
        deploy_target = "none"
    else:
        deploy_target = None

    # Auth scope from who uses it (context for the framework, not a run flag).
    auth_scope = {"public": "public", "team": "team", "just_me": "none"}.get(users)

    # Supabase env questions only when a real DB AND on the web.
    if profile == "supabase-nextjs" and run_location == "web":
        env_questions = list(SUPABASE_ENV_QUESTIONS)
    else:
        env_questions = []

    answered = [q for q in BRIEF_QUESTIONS if brief.get(q) is not None]
    remaining = [q for q in BRIEF_QUESTIONS if brief.get(q) is None] + list(_ALWAYS_ASK)

    return {
        "has_brief": True,
        "brief": brief,
        "profile": profile,
        "profile_reason": profile_reason,
        "deploy_target": deploy_target,
        "auth_scope": auth_scope,
        "answered": answered,
        "remaining_questions": remaining,
        "env_questions": env_questions,
    }


def _no_brief_result() -> dict:
    """The legacy-interview result: every brief question still remaining."""
    return {
        "has_brief": False,
        "brief": {q: None for q in BRIEF_QUESTIONS},
        "profile": None,
        "profile_reason": "no brief -> legacy interview",
        "deploy_target": None,
        "auth_scope": None,
        "answered": [],
        "remaining_questions": list(BRIEF_QUESTIONS) + list(_ALWAYS_ASK),
        "env_questions": [],
    }


_KV_RE = re.compile(r"^\s*[-*]?\s*([A-Za-z_][\w -]*?)\s*[:=]\s*(.+?)\s*$")
# Greedy body + trailing-fence anchor so a nested `{...}` parses in full.
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _parse_text_brief(text: str) -> dict:
    """Parse a markdown/plain-text brief payload.

    Preference order: a fenced ```json {...}``` block, then ``key: value``
    lines for the four fields, else the whole text as description-only.
    """
    fence = _FENCE_RE.search(text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except (ValueError, json.JSONDecodeError):
            pass

    fields = {}
    prose = []
    for line in text.splitlines():
        m = _KV_RE.match(line)
        key = ""
        if m:
            key = m.group(1).strip().lower().replace(" ", "_").replace("-", "_")
            if key == "location":
                key = "run_location"
        if key in BRIEF_QUESTIONS:
            fields[key] = m.group(2).strip()
        elif line.strip():
            prose.append(line.strip())  # keep non-kv prose as the description
    if prose and not fields.get("description"):
        fields["description"] = " ".join(prose)
    return fields or {"description": text.strip()}


def load_brief(source: Optional[Union[str, dict]]) -> Optional[dict]:
    """Load a raw brief from a dict, inline payload, or file path.

    Returns the raw (un-normalized) brief dict, or None — meaning "no usable
    brief, run the legacy interview" — when no brief was given OR an explicit
    file reference cannot be read. Files are read utf-8-sig (BOM-tolerant).
    """
    if source is None:
        return None
    if isinstance(source, dict):
        return source

    text = str(source).strip()
    if not text:
        return None

    # Inline JSON payload.
    if text.startswith("{"):
        try:
            return json.loads(text)
        except (ValueError, json.JSONDecodeError):
            return {"description": text}

    # Explicit file reference: @-prefixed, OR a bare path whose suffix is a
    # recognized brief format. Read it, or DEGRADE to the legacy interview
    # (None) — never turn an unreadable/misplaced path into a description
    # (the K2c contract: a missing brief file re-asks, it does not build the
    # path string as the app brief).
    path_str = text[1:] if text.startswith("@") else text
    suffix = Path(path_str).suffix.lower()
    if text.startswith("@") or suffix in _BRIEF_SUFFIXES:
        try:
            path = Path(path_str)
            if (
                suffix in _BRIEF_SUFFIXES
                and path.is_file()
                and path.stat().st_size <= _MAX_BRIEF_BYTES
            ):
                content = path.read_text(encoding="utf-8-sig")
                if suffix == ".json":
                    try:
                        return json.loads(content)
                    except (ValueError, json.JSONDecodeError):
                        return _parse_text_brief(content)
                return _parse_text_brief(content)
        except (OSError, ValueError):
            pass
        return None

    # An inline payload (markdown/fenced-json/key:value) or a plain sentence.
    return _parse_text_brief(path_str)


def intake(source: Optional[Union[str, dict]]) -> dict:
    """Full brief-intake: load + normalize + map.

    ``source`` is a brief dict, an inline JSON/text payload, a file path
    (optionally ``@``-prefixed), or None. None -> legacy-interview result.
    """
    raw = load_brief(source)
    if raw is None:
        return _no_brief_result()
    return map_brief(normalize_brief(raw))


def main() -> int:
    parser = argparse.ArgumentParser(description="Brief-intake for shipwright-run")
    parser.add_argument(
        "--brief",
        default=None,
        help="Brief file path (optionally @-prefixed) or inline JSON/text payload",
    )
    parser.add_argument("--project-root", help="Project root (unused; accepted for parity)")
    args = parser.parse_args()

    result = intake(args.brief)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
