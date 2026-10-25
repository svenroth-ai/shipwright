#!/usr/bin/env python3
"""Brief-intake for shipwright-run (K2c).

The WebUI Intent Wizard (K2) hands ``/shipwright-run`` a pre-delivered *brief*
(file path or inline payload): description (free text), users (just_me|team|public),
persistence (yes|no|unsure), run_location (local|web). This module maps the answers to
profile + deploy/env and reports which interview questions are still missing.

Mapping (concept §2.1/§2.2): persistence=yes -> supabase-nextjs; no/unsure ->
vite-hono (zero-signup local default); run_location web -> deploy target set,
local -> "none"; supabase env questions asked ONLY when supabase AND web.

No brief -> legacy interview unchanged (AC3); an unreadable brief FILE degrades the
same way. A DIRECTORY is a Brief package (``brief_dir_intake.py``): approval + hash are
verified and a bad one is refused loudly. CLI: --brief <path|payload|dir>.
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Optional, Union

# The four wizard answers, in interview order (the questions a brief file can pre-answer).
BRIEF_QUESTIONS = ["description", "users", "persistence", "run_location"]

# Non-brief question the wizard never sets -> always still asked.
_ALWAYS_ASK = ["autonomy"]

# required_env_vars.build of shared/profiles/supabase-nextjs.json.
SUPABASE_ENV_QUESTIONS = [
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
]

# A brief FILE is only read with a parseable suffix and a sane size (no stray `@/etc/passwd`).
_BRIEF_SUFFIXES = {".json", ".md", ".txt"}
_MAX_BRIEF_BYTES = 256 * 1024

# Synonym tables: lower-cased answer text -> canonical value (human-facing labels allowed).
_USERS_SYNONYMS = {
    "just_me": "just_me", "just me": "just_me", "only me": "just_me", "me": "just_me", "myself": "just_me",
    "solo": "just_me", "team": "team", "my team": "team", "internal": "team", "colleagues": "team",
    "coworkers": "team", "public": "public", "customers": "public", "clients": "public",
    "customers / public": "public", "customers/public": "public", "everyone": "public",
}
_PERSISTENCE_SYNONYMS = {
    "yes": "yes", "y": "yes", "true": "yes", "no": "no", "n": "no", "false": "no",
    "unsure": "unsure", "not sure": "unsure", "not sure yet": "unsure", "maybe": "unsure",
    "dunno": "unsure", "don't know": "unsure", "dont know": "unsure",
}
_RUN_LOCATION_SYNONYMS = {
    "local": "local", "machine": "local", "my machine": "local", "just my machine": "local",
    "my computer": "local", "localhost": "local", "web": "web", "cloud": "web", "online": "web",
    "internet": "web", "hosted": "web", "deployed": "web", "on the web": "web",
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
    """Normalize a raw brief to the four canonical fields (unknown -> None; non-dict degrades)."""
    raw = raw if isinstance(raw, dict) else {}
    desc = raw.get("description")
    if desc is not None and not isinstance(desc, str):
        desc = str(desc)  # a non-string description is never silently a non-str
    if isinstance(desc, str) and not desc.strip():
        desc = None
    return {
        "description": desc,
        "users": _canonical("users", raw.get("users")),
        "persistence": _canonical("persistence", raw.get("persistence")),
        "run_location": _canonical("run_location", raw.get("run_location")),
    }


def map_brief(brief: dict, explicit: Optional[dict] = None) -> dict:  # normalized brief -> profile/deploy/env + questions
    persistence = brief.get("persistence")
    run_location = brief.get("run_location")
    users = brief.get("users")

    # Profile: persistence drives the DB decision; vite-hono is the zero-signup default.
    if persistence == "yes":
        profile, profile_reason = "supabase-nextjs", "persistence=yes -> real database (supabase-nextjs)"
    elif persistence in ("no", "unsure"):
        profile = "vite-hono"
        profile_reason = "persistence=%s -> local zero-signup default (vite-hono)" % persistence
    else:
        profile = None
        profile_reason = "persistence unknown -> profile still to decide"
    if explicit and "profile" in explicit:  # a profile the brief names beats inference (brief_profile.py)
        profile, profile_reason = explicit["profile"], explicit["reason"]

    # Deploy target from run-location.
    deploy_target = {"web": "jelastic-dev", "local": "none"}.get(run_location)

    auth_scope = {"public": "public", "team": "team", "just_me": "none"}.get(users)

    env_questions = list(SUPABASE_ENV_QUESTIONS) if profile == "supabase-nextjs" and run_location == "web" else []

    answered = [q for q in BRIEF_QUESTIONS if brief.get(q) is not None]
    remaining = [q for q in BRIEF_QUESTIONS if brief.get(q) is None] + list(_ALWAYS_ASK)

    result = {
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
    result.update(explicit["extra"] if explicit else {})
    return result


def _no_brief_result() -> dict:
    return {  # the legacy interview: every brief question still remaining
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


_KEY_ALIASES = {"location": "run_location"}
_KV_RE = re.compile(r"^\s*[-*]?\s*([A-Za-z_][\w -]*?)\s*[:=]\s*(.+?)\s*$")
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)  # greedy body + trailing-fence anchor: a nested {...} parses in full


def _parse_text_brief(text: str) -> dict:
    """Parse a text brief: fenced ```json``` block, else ``key: value`` lines, else description-only."""
    fence = _FENCE_RE.search(text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except (ValueError, json.JSONDecodeError):
            pass

    fields, meta, prose = {}, {"_text": text.strip()}, []  # meta: side channel for brief_profile.py, never a brief answer
    for line in text.splitlines():
        m = _KV_RE.match(line)
        key = ""
        if m:
            key = m.group(1).strip().lower().replace(" ", "_").replace("-", "_")
            key = _KEY_ALIASES.get(key, key)
            if key == "profile" and line.lstrip()[:1] not in "-*":  # only a hint, and the line stays prose
                meta["profile_hint"] = m.group(2).strip()
        if key in BRIEF_QUESTIONS or key == "stack_profile":
            meta["_dup"] = meta.get("_dup") or (key == "stack_profile" and key in fields)  # two lines: refused
            fields[key] = m.group(2).strip()
        elif line.strip():
            prose.append(line.strip())  # keep non-kv prose as the description
    if prose and not fields.get("description"):
        fields["description"] = " ".join(prose)
    return {**(fields or {"description": text.strip()}), **meta}


def load_brief(source: Optional[Union[str, dict]]) -> Optional[dict]:
    """Raw brief dict from a dict, inline payload or file (utf-8-sig), or None = legacy interview."""
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

    # Explicit file reference (@-prefixed or a recognized suffix): read it, or DEGRADE to the
    # legacy interview (None) -- never turn an unreadable path into the app description.
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


def _sibling(stem: str):
    """A sibling module loaded by file path under a private name (ADR-045: never ``import lib``)."""
    name = "_shipwright_" + stem
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(stem + ".py"))
        sys.modules[name] = mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def _package_intake(source, root):
    """Opt-in (``package=True``): a one-line source naming an existing directory, or a space-free one
    ending in a slash, is a Brief package (``brief_dir_intake.py``)."""
    text = source.strip() if isinstance(source, str) else ""
    if not text or text[0] in "{@" or len(text) > 240 or any(c in text for c in "\n\r"):
        return None
    try:
        is_dir = (Path(root) / text).is_dir()
    except (OSError, ValueError):
        is_dir = False
    if not (is_dir or (text[-1] in "/\\" and " " not in text)):
        return None
    return _sibling("brief_dir_intake").intake_dir(text, root)


def intake(source: Optional[Union[str, dict]], project_root: str = ".", package: bool = False) -> dict:
    """Full brief-intake: load + normalize + map (dict, payload, file path; a package dir if ``package``)."""
    result = _package_intake(source, project_root) if package else None
    if result is not None:
        return result
    raw = load_brief(source)
    if raw is None:
        return _no_brief_result()
    explicit = None
    if "rofile" in str(raw).lower():  # only a brief that can name a profile touches brief_profile.py and the resolver
        try:
            explicit = _sibling("brief_profile").select(raw, project_root)
        except Exception as exc:  # missing or broken sibling: the refusal shape of brief_profile._error, exit 3
            msg = " ".join(re.sub(r"[^ -~]", " ", str(exc)).split())[:300]
            explicit = {"profile": None, "reason": "profile check unavailable", "extra": {
                "warnings": [msg], "profile_error": {"code": "resolver_unavailable", "message": msg},
                "refused": True, "code": "profile_unusable", "message": msg, "issues": []}}
    return map_brief(normalize_brief(raw), explicit)


def main() -> int:
    parser = argparse.ArgumentParser(description="Brief-intake for shipwright-run")
    parser.add_argument("--brief", default=None, help="Brief file path (optionally @-prefixed) or inline JSON/text payload")
    parser.add_argument("--project-root", default=".", help="Project root (a package dir resolves here)")
    args = parser.parse_args()

    try:
        result = intake(args.brief, args.project_root, package=True)
    except Exception as exc:  # BriefRefused (package route): fail loudly, never degrade
        if not hasattr(exc, "as_dict"):
            raise
        print(json.dumps(exc.as_dict(), indent=2))
        return 3
    print(json.dumps(result, indent=2))
    return 3 if result.get("profile_error") else 0  # a named profile that cannot be used is loud


if __name__ == "__main__":
    sys.exit(main())
