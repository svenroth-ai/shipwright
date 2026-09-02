#!/usr/bin/env python3
"""Send a fixed, non-sensitive GLM 5.3 request through the production ZDR route.

Mirrored the verification discipline of the now-removed
shared/scripts/tools/probe_deepseek_zdr.py (deleted in
iterate-2026-09-02-glm-plan-code-review-swap, once GLM 5.3 replaced DeepSeek as
the plan/code-review cascade's own second reviewer identity) for the PR-review
gate's GLM arm. Lives in this plugin's own scripts/tools/ rather than shared/
because this probe reads the model string straight from
pr_review_openrouter.GLM_MODEL — the PR-review gate's own operator-overridable
model, resolved independently of the cascade's `external_review_routing`
bindings even though both now define a "glm" reviewer identity.

Data-policy verification (OpenRouter's all-providers API, 2026-09-01) confirms
novita/together are zero-retention for GLM 5.3 in general; it does not confirm
either actually SERVES this specific model at request time. This probe closes
that gap: a real completion through the production `extra_body` route,
asserting the provider OpenRouter actually selected is one of the two approved
ones (iterate-2026-09-01-pr-review-glm-model, Stage-3 doubt review).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_PLUGIN_LIB = Path(__file__).resolve().parents[1] / "lib"
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
for _path in (_PLUGIN_LIB, _SHARED_LIB):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from env import load_shipwright_env  # type: ignore[import-not-found]  # noqa: E402
from external_review_config import load_review_config  # noqa: E402
from external_review_degraded import DEFAULT_TIMEOUT_SECONDS  # noqa: E402
from external_review_routing import glm_openrouter_extra_body  # noqa: E402
from pr_review_openrouter import GLM_MODEL  # noqa: E402
from review_record_schema import is_safe_run_id  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_PROBE_PROMPT = "Return only this token, with no explanation: ZDR_PROBE_OK"
_PROVIDER_ALIASES = {
    "novita": "novita",
    "novitaai": "novita",
    "together": "together",
    "togetherai": "together",
}


def _selected_provider(response: object) -> str | None:
    raw = getattr(response, "provider", None)
    if raw is None:
        extra = getattr(response, "model_extra", None)
        raw = extra.get("provider") if isinstance(extra, dict) else None
    if not isinstance(raw, str):
        return None
    compact = "".join(ch for ch in raw.lower() if ch.isalnum())
    return _PROVIDER_ALIASES.get(compact)


def _base_evidence(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    extra_body = glm_openrouter_extra_body(config)
    return extra_body, {
        "schema_version": 1,
        "model": GLM_MODEL,
        "provider_policy": extra_body["provider"],
    }


def run_probe(config: dict[str, Any], *, api_key: str | None) -> dict[str, Any]:
    """Run one bounded probe and return only sanitized evidence."""
    request_attempted = False
    try:
        extra_body, evidence = _base_evidence(config)
    except Exception as exc:  # policy/config failure; no request has been sent
        return {
            "schema_version": 1,
            "status": "degraded",
            "reason": "glm_routing_policy_invalid",
            "error_type": type(exc).__name__,
            "live_request_sent": False,
            "live_request_attempted": False,
        }

    if not api_key:
        return {
            **evidence,
            "status": "skipped",
            "reason": "openrouter_credential_unavailable",
            "live_request_sent": False,
            "live_request_attempted": False,
            "selected_provider": None,
        }

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=config.get("llm_client", {}).get(
                "timeout_seconds", DEFAULT_TIMEOUT_SECONDS
            ),
        )
        request_attempted = True
        response = client.chat.completions.create(
            model=evidence["model"],
            messages=[
                {
                    "role": "system",
                    "content": "Follow the response format exactly; output no analysis.",
                },
                {"role": "user", "content": _PROBE_PROMPT},
            ],
            max_tokens=128,
            temperature=0,
            extra_body=extra_body,
        )
        selected = _selected_provider(response)
        content = response.choices[0].message.content
        normalized = (content or "").strip().strip("`'\". ")
        response_ok = normalized == "ZDR_PROBE_OK"
        if selected not in extra_body["provider"]["only"]:
            return {
                **evidence,
                "status": "degraded",
                "reason": "selected_provider_not_approved",
                "live_request_sent": True,
                "live_request_attempted": True,
                "selected_provider": selected,
                "response_valid": response_ok,
            }
        return {
            **evidence,
            "status": "success" if response_ok else "degraded",
            "reason": None if response_ok else "synthetic_response_mismatch",
            "live_request_sent": True,
            "live_request_attempted": True,
            "selected_provider": selected,
            "response_valid": response_ok,
        }
    except Exception as exc:  # never persist provider/SDK exception text
        return {
            **evidence,
            "status": "degraded",
            "reason": "openrouter_request_failed",
            "error_type": type(exc).__name__,
            "live_request_sent": False,
            "live_request_attempted": request_attempted,
            "selected_provider": None,
        }


def _evidence_path(project_root: Path, run_id: str) -> Path:
    return (
        project_root
        / ".shipwright"
        / "planning"
        / "iterate"
        / run_id
        / "glm-zdr-probe.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not is_safe_run_id(args.run_id):
        parser.error("--run-id must be one safe path component")

    project_root = Path(args.project_root).resolve()
    load_shipwright_env(project_root)
    config = load_review_config(project_root=project_root)
    payload = run_probe(config, api_key=os.environ.get("OPENROUTER_API_KEY"))
    output = _evidence_path(project_root, args.run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "evidence_path": str(output)}, indent=2))
    return 1 if payload["status"] == "degraded" else 0


if __name__ == "__main__":
    raise SystemExit(main())
