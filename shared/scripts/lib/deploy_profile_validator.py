"""
Deploy Profile validator — pure validation library.

Validates a Shipwright deploy profile against the JSON-Schema
(shared/profiles/deploy-profile.schema.json) plus a layer of semantic checks
that JSON-Schema cannot express cleanly:

- shipped/stub vs confidence/client consistency
- client.entrypoint repo-relative + path-traversal guard
- filename ↔ target_id consistency
- duplicate target_id across profiles (in --all mode)
- duplicate env-var names within or across required/optional lists
- (in --strict mode) client.entrypoint resolves to a real file under repo_root

The library exposes a single `validate()` function. CLI wrapping lives in
`shared/scripts/tools/validate_deploy_profile.py`.

Remote $ref resolution in the underlying jsonschema library is disabled by
passing a Registry that refuses retrieval — schemas in this validator MUST be
fully self-contained.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator
from referencing import Registry


@dataclass(frozen=True)
class ValidationError:
    """One rule violation. Errors only — no severity levels (YAGNI)."""

    json_pointer: str
    message: str
    profile_path: Path | None = None

    def __str__(self) -> str:
        prefix = f"FAIL {self.profile_path} :: " if self.profile_path else "FAIL :: "
        return f"{prefix}{self.json_pointer or '$'} :: {self.message}"


def _refuse_remote_retrieve(uri: str):  # pragma: no cover - never called when schemas are local
    raise RuntimeError(f"Remote $ref resolution refused: {uri}")


_OFFLINE_REGISTRY = Registry(retrieve=_refuse_remote_retrieve)


def _to_pointer(absolute_path: Iterable[object]) -> str:
    """Convert a jsonschema absolute_path (deque of keys/indices) to a JSON pointer string."""
    parts = []
    for segment in absolute_path:
        if isinstance(segment, int):
            parts.append(str(segment))
        else:
            # Escape per RFC 6901
            escaped = str(segment).replace("~", "~0").replace("/", "~1")
            parts.append(escaped)
    return "/" + "/".join(parts) if parts else ""


def _structural_errors(
    profile: dict,
    schema: dict,
    *,
    profile_path: Path | None,
) -> list[ValidationError]:
    """JSON-Schema-level errors (multi-error: collect all, not stop-at-first)."""
    validator = Draft202012Validator(schema, registry=_OFFLINE_REGISTRY)
    out: list[ValidationError] = []
    for err in validator.iter_errors(profile):
        out.append(
            ValidationError(
                json_pointer=_to_pointer(err.absolute_path),
                message=err.message,
                profile_path=profile_path,
            )
        )
    return out


def _semantic_errors(
    profile: dict,
    *,
    profile_path: Path | None,
    repo_root: Path | None,
    strict: bool,
    known_target_ids: set[str] | None,
) -> list[ValidationError]:
    """Cross-field invariants that JSON-Schema can't express cleanly.

    These run on top of structural validation and assume the profile is a dict
    (callers typically only run semantic checks if the file at least parses).
    """
    out: list[ValidationError] = []

    status = profile.get("implementation_status")
    confidence = profile.get("confidence")
    client = profile.get("client")
    target_id = profile.get("target_id")

    # Semantic rule (a): shipped → confidence MUST be 'verified'.
    # Schema also expresses this via allOf, but we add a clearer message here
    # so the operator-facing error doesn't read like a JSON-Schema oneOf trace.
    if status == "shipped" and confidence is not None and confidence != "verified":
        out.append(
            ValidationError(
                json_pointer="/confidence",
                message=(
                    f"shipped profiles must declare confidence='verified' (got '{confidence}')."
                ),
                profile_path=profile_path,
            )
        )

    # Semantic rule (b): stub → confidence MUST be documented or inferred.
    if status == "stub" and confidence is not None and confidence == "verified":
        out.append(
            ValidationError(
                json_pointer="/confidence",
                message="stub profiles cannot declare confidence='verified' — use 'documented' or 'inferred'.",
                profile_path=profile_path,
            )
        )

    # Semantic rule (c): shipped → client must be non-null object.
    if status == "shipped" and client is None:
        out.append(
            ValidationError(
                json_pointer="/client",
                message="shipped profiles must declare a non-null client (entrypoint + runner).",
                profile_path=profile_path,
            )
        )

    # Semantic rule (d): client.entrypoint must be repo-relative.
    if isinstance(client, dict):
        entrypoint = client.get("entrypoint")
        if isinstance(entrypoint, str) and entrypoint:
            # Reject absolute paths (POSIX or Windows).
            if Path(entrypoint).is_absolute() or entrypoint.startswith(("/", "\\")):
                out.append(
                    ValidationError(
                        json_pointer="/client/entrypoint",
                        message=f"client.entrypoint must be repo-relative, not absolute: {entrypoint!r}",
                        profile_path=profile_path,
                    )
                )
            elif ".." in Path(entrypoint).parts:
                out.append(
                    ValidationError(
                        json_pointer="/client/entrypoint",
                        message=f"client.entrypoint must not contain '..' (path-traversal guard): {entrypoint!r}",
                        profile_path=profile_path,
                    )
                )
            elif strict and repo_root is not None:
                # Semantic rule (e): --strict file-existence check, bounded to repo_root.
                resolved = (repo_root / entrypoint).resolve()
                try:
                    resolved.relative_to(repo_root.resolve())
                except ValueError:
                    out.append(
                        ValidationError(
                            json_pointer="/client/entrypoint",
                            message=(
                                f"--strict: resolved client.entrypoint escapes repo_root "
                                f"({resolved} not under {repo_root.resolve()})"
                            ),
                            profile_path=profile_path,
                        )
                    )
                else:
                    if not resolved.is_file():
                        out.append(
                            ValidationError(
                                json_pointer="/client/entrypoint",
                                message=f"--strict: client.entrypoint does not resolve to a file: {resolved}",
                                profile_path=profile_path,
                            )
                        )

    # Semantic rule (f): filename ↔ target_id consistency.
    if profile_path is not None and isinstance(target_id, str):
        expected_stem = profile_path.stem
        if expected_stem != target_id:
            out.append(
                ValidationError(
                    json_pointer="/target_id",
                    message=(
                        f"filename stem {expected_stem!r} must equal target_id "
                        f"{target_id!r}"
                    ),
                    profile_path=profile_path,
                )
            )

    # Semantic rule (g): duplicate target_id across profiles in --all mode.
    # Detection only — registration into known_target_ids happens in `validate()`
    # AFTER all checks pass, so a malformed profile cannot "reserve" an id and
    # cause a later valid profile to be misreported as a duplicate.
    if known_target_ids is not None and isinstance(target_id, str):
        if target_id in known_target_ids:
            out.append(
                ValidationError(
                    json_pointer="/target_id",
                    message=f"duplicate target_id {target_id!r} found across profiles in --all run",
                    profile_path=profile_path,
                )
            )

    # Semantic rule (h): duplicate env-var names within / across required/optional lists.
    auth = profile.get("auth")
    if isinstance(auth, dict):
        seen: dict[str, str] = {}  # name -> "required" | "optional"
        for bucket in ("required_env_vars", "optional_env_vars"):
            entries = auth.get(bucket)
            if not isinstance(entries, list):
                continue
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if not isinstance(name, str):
                    continue
                if name in seen:
                    out.append(
                        ValidationError(
                            json_pointer=f"/auth/{bucket}/{idx}/name",
                            message=(
                                f"duplicate env-var name {name!r} (also appears in "
                                f"auth.{seen[name]}_env_vars)"
                            ),
                            profile_path=profile_path,
                        )
                    )
                else:
                    seen[name] = "required" if bucket == "required_env_vars" else "optional"

    return out


def validate(
    profile: dict,
    schema: dict,
    *,
    profile_path: Path | None = None,
    strict: bool = False,
    repo_root: Path | None = None,
    known_target_ids: set[str] | None = None,
) -> list[ValidationError]:
    """Validate one profile against the schema + apply semantic checks.

    Args:
        profile: Parsed profile dict.
        schema: Parsed schema dict.
        profile_path: Profile file path (for filename ↔ target_id check + error
            messages). None when validating an in-memory dict (semantic check
            'f' is skipped).
        strict: Enable --strict mode: client.entrypoint must resolve to a real
            file under repo_root. Requires repo_root.
        repo_root: Repository root for --strict mode.
        known_target_ids: Optional set passed across multiple validate() calls
            in --all mode to track duplicates. Mutated in-place: target_id is
            added on first sight; subsequent calls flag duplicates.

    Returns:
        List of ValidationError. Empty list = profile is valid.
    """
    structural = _structural_errors(profile, schema, profile_path=profile_path)
    semantic = _semantic_errors(
        profile,
        profile_path=profile_path,
        repo_root=repo_root,
        strict=strict,
        known_target_ids=known_target_ids,
    )
    all_errors = structural + semantic

    # Register target_id only if the profile is otherwise clean (no errors at all).
    # See review finding: duplicate-id tracking should not "reserve" an id from a
    # malformed profile and falsely flag a later valid profile as a duplicate.
    if (
        not all_errors
        and known_target_ids is not None
        and isinstance(profile.get("target_id"), str)
    ):
        known_target_ids.add(profile["target_id"])

    return all_errors
