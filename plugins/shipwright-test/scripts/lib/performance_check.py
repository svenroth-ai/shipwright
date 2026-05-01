#!/usr/bin/env python3
"""Performance budget check — Lighthouse (via Playwright) + bundle size.

Profile-driven, project-overridable performance gate. Runs Lighthouse against
a live dev URL via a small Node script that reuses the project's Playwright
Chromium (no extra browser install). Bundle size is measured in pure Python
by walking the profile-declared `build_output_dir`.

Output: a single JSON object on stdout (see RESULT_SCHEMA below). Exit code
is 0 unless `gate=block` AND any non-skipped check failed.

CLI:
    uv run performance_check.py \\
        --cwd <project> \\
        --profile-path <path-to-profile.json> \\
        --dev-url <url> \\
        --gate <warn|block|inherit>

Test seam (RESTRICTED — see _test_seam_active):
    SHIPWRIGHT_PERF_LHCI_FAKE=<path-to-saved-lhr.json>
    SHIPWRIGHT_TEST_MODE=1
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

BUILTIN_DEFAULTS: dict[str, Any] = {
    "enabled": False,  # opt-in via profile or test_config
    "lighthouse": {
        "min_score": 85,
        "lcp_max_ms": 2500,
        # Where Node should resolve the `playwright` module from. Relative to
        # --cwd (project root). Empty / unset → project root. Monorepo layouts
        # (e.g. vite-hono with client/ + server/) set this to "client".
        "playwright_cwd": "",
    },
    "bundle": {
        "max_kb_gz": 250,
        "build_output_dir": "",  # MUST be set by profile/config; "" = skip bundle
    },
    "gate": "warn",
}

VALID_GATES = ("warn", "block")

SKIP_REASON_PROFILE_OPTS_OUT = "profile opts out (testing.performance.enabled is false)"
SKIP_REASON_NO_DEV_URL = "no dev_url available"
SKIP_REASON_LHCI_UNAVAILABLE = "lighthouse_unavailable"
SKIP_REASON_NO_BUILD_DIR = "no build artifacts found"
SKIP_REASON_NO_BUNDLE_MATCH = "no bundle assets matched"

LIGHTHOUSE_SUBPROCESS_TIMEOUT_S = 180

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


# ── Config Resolution (precedence: CLI > test_config > profile > builtin) ─────

def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge: nested dicts merge field-by-field, scalars replace."""
    out = deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def resolve_config(
    profile_perf: dict[str, Any] | None,
    test_config_perf: dict[str, Any] | None,
    cli_gate: str | None,
) -> dict[str, Any]:
    """Resolve effective config. Deep-merge at nested-block level."""
    cfg = deepcopy(BUILTIN_DEFAULTS)
    if profile_perf:
        cfg = _deep_merge(cfg, profile_perf)
    if test_config_perf:
        cfg = _deep_merge(cfg, test_config_perf)
    if cli_gate and cli_gate != "inherit":
        if cli_gate not in VALID_GATES:
            raise ValueError(f"Invalid gate '{cli_gate}'; expected one of {VALID_GATES}")
        cfg["gate"] = cli_gate

    if not cfg.get("enabled"):
        cfg["skip_reason"] = SKIP_REASON_PROFILE_OPTS_OUT
    return cfg


# ── dev_url validation (Review Finding 9) ─────────────────────────────────────

def validate_dev_url(url: str) -> None:
    """Reject non-http/https schemes; warn on non-loopback hosts."""
    if not url:
        raise ValueError("dev_url is empty")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"dev_url scheme must be http or https, got '{parsed.scheme}' in {url!r}"
        )
    if not parsed.netloc:
        raise ValueError(f"dev_url has no host: {url!r}")

    host = parsed.hostname or ""
    if host not in LOOPBACK_HOSTS:
        sys.stderr.write(
            f"WARNING: Lighthouse target is non-loopback: {host} — "
            "verify this is intentional (the runner will proceed).\n"
        )


def preflight_dev_url(url: str, timeout_s: float = 5.0) -> tuple[bool, str]:
    """HTTP HEAD probe — returns (reachable, diagnostic).

    Connection / DNS / timeout errors → (False, reason).
    Any HTTP response (incl. 404, 500) → (True, "") — Lighthouse handles those.
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout_s):  # noqa: S310 — caller-controlled URL
            return True, ""
    except urllib.error.HTTPError:
        return True, ""  # server responded — Lighthouse can audit error pages
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


# ── Lighthouse-report parsing ─────────────────────────────────────────────────

def parse_lighthouse_report(lhr: dict[str, Any]) -> dict[str, Any]:
    """Extract performance score (0-100 int) and LCP (ms, int) from LHR JSON.

    Returns {"score": int|None, "lcp_ms": int|None, "error": str|None}.
    """
    try:
        raw_score = lhr["categories"]["performance"]["score"]
    except (KeyError, TypeError):
        return {"score": None, "lcp_ms": None,
                "error": "missing categories.performance.score in LHR"}
    if raw_score is None:
        return {"score": None, "lcp_ms": None,
                "error": "categories.performance.score is null"}
    score = round(float(raw_score) * 100)

    try:
        raw_lcp = lhr["audits"]["largest-contentful-paint"]["numericValue"]
    except (KeyError, TypeError):
        return {"score": score, "lcp_ms": None,
                "error": "missing audits.largest-contentful-paint.numericValue"}

    return {"score": score, "lcp_ms": round(float(raw_lcp)), "error": None}


# ── Bundle measurement ───────────────────────────────────────────────────────

_BUNDLE_INCLUDE_SUFFIXES = (".js", ".css")
_BUNDLE_EXCLUDE_SUFFIXES = (".map", ".gz", ".br")


def measure_bundle(build_dir: Path) -> dict[str, Any]:
    """Walk build_dir, sum gzip-compressed sizes of *.js / *.css.

    Excludes: source maps, precompressed siblings (.gz, .br) — Review
    Finding 8. Returns structured result; 0-files match → skipped (Review
    Finding 3), NOT silent passing 0 KB.
    """
    if not build_dir.exists():
        return {
            "ran": False, "skipped": True,
            "skip_reason": f"{SKIP_REASON_NO_BUILD_DIR}: directory missing: {build_dir}",
            "total_kb_gz": 0.0, "files_measured": 0, "files": [],
            "passed": True,
        }
    if not build_dir.is_dir():
        return {
            "ran": False, "skipped": True,
            "skip_reason": f"{SKIP_REASON_NO_BUILD_DIR}: not a directory: {build_dir}",
            "total_kb_gz": 0.0, "files_measured": 0, "files": [],
            "passed": True,
        }

    matched: list[Path] = []
    for p in build_dir.rglob("*"):
        if not p.is_file():
            continue
        # Exclude precompressed siblings + sourcemaps
        if any(p.name.endswith(suf) for suf in _BUNDLE_EXCLUDE_SUFFIXES):
            continue
        if not any(p.name.endswith(suf) for suf in _BUNDLE_INCLUDE_SUFFIXES):
            continue
        matched.append(p)

    if not matched:
        return {
            "ran": True, "skipped": True,
            "skip_reason": (
                f"{SKIP_REASON_NO_BUNDLE_MATCH}: 0 *.js / *.css files in {build_dir}"
            ),
            "total_kb_gz": 0.0, "files_measured": 0, "files": [],
            "passed": True,
        }

    total_bytes = 0
    for p in matched:
        try:
            raw = p.read_bytes()
        except OSError as exc:
            return {
                "ran": True, "skipped": True,
                "skip_reason": f"failed to read {p}: {exc}",
                "total_kb_gz": 0.0, "files_measured": 0, "files": [],
                "passed": True,
            }
        total_bytes += len(gzip.compress(raw, compresslevel=9))

    total_kb_gz = round(total_bytes / 1024, 2)
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "total_kb_gz": total_kb_gz,
        "files_measured": len(matched),
        "files": [str(p.relative_to(build_dir)) for p in matched],
        "measurement_semantic": (
            "gzipped *.js + *.css payload — excludes assets, source-maps, "
            "precompressed siblings"
        ),
    }


# ── Gate evaluation ──────────────────────────────────────────────────────────

def evaluate_gate(results: dict[str, Any], gate: str) -> bool:
    """Return overall success.

    `warn` always returns True (failures logged, pipeline continues).
    `block` returns False if any non-skipped layer failed.
    """
    if gate == "warn":
        return True
    if gate != "block":
        raise ValueError(f"Invalid gate '{gate}'; expected one of {VALID_GATES}")

    lh = results.get("lighthouse", {})
    if lh.get("ran") and not lh.get("skipped"):
        if not lh.get("score_passed", True) or not lh.get("lcp_passed", True):
            return False

    bundle = results.get("bundle", {})
    if bundle.get("ran") and not bundle.get("skipped"):
        if not bundle.get("passed", True):
            return False

    return True


# ── Test seam (Review Finding 10) ─────────────────────────────────────────────

def _test_seam_active() -> bool:
    """SHIPWRIGHT_PERF_LHCI_FAKE honored only with SHIPWRIGHT_TEST_MODE=1
    AND a path that contains a loadable fake LHR.

    Logs WARNING + returns False on any misconfiguration (NEVER silent-skip
    nor lighthouse_unavailable: explicit fall-through to real run).
    """
    fake = os.environ.get("SHIPWRIGHT_PERF_LHCI_FAKE", "")
    if not fake:
        return False

    if os.environ.get("SHIPWRIGHT_TEST_MODE") != "1":
        sys.stderr.write(
            "WARNING: SHIPWRIGHT_PERF_LHCI_FAKE is set but "
            "SHIPWRIGHT_TEST_MODE != 1 -- ignoring (real Lighthouse will run).\n"
        )
        return False

    fake_path = Path(fake)
    if not fake_path.exists():
        sys.stderr.write(
            f"WARNING: SHIPWRIGHT_PERF_LHCI_FAKE points at non-existent path "
            f"{fake_path} -- ignoring (real Lighthouse will run).\n"
        )
        return False

    # Validate that the path actually yields a loadable LHR — prevents the
    # "seam active but file empty/invalid → silent lighthouse_unavailable"
    # failure mode (external code-review Finding 5).
    if fake_path.is_dir():
        candidates = sorted(fake_path.glob("lhr-*.json"))
        if not candidates:
            sys.stderr.write(
                f"WARNING: SHIPWRIGHT_PERF_LHCI_FAKE directory {fake_path} "
                f"contains no lhr-*.json -- ignoring (real Lighthouse will run).\n"
            )
            return False
    elif not fake_path.is_file():
        sys.stderr.write(
            f"WARNING: SHIPWRIGHT_PERF_LHCI_FAKE path {fake_path} is neither "
            f"file nor directory -- ignoring (real Lighthouse will run).\n"
        )
        return False

    return True


def _load_fake_lhr() -> dict[str, Any] | None:
    """Read fake LHR fixture (called only when _test_seam_active() is True).

    Accepts either a single JSON file path OR a directory containing
    `lhr-*.json` (returns the first match alphabetically).
    """
    fake_path = Path(os.environ["SHIPWRIGHT_PERF_LHCI_FAKE"])
    if fake_path.is_file():
        return json.loads(fake_path.read_text(encoding="utf-8"))
    if fake_path.is_dir():
        candidates = sorted(fake_path.glob("lhr-*.json"))
        if not candidates:
            return None
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    return None


# ── Lighthouse runner orchestration ──────────────────────────────────────────

def _perf_node_dir() -> Path:
    """Directory containing lighthouse-runner.mjs + its package.json."""
    return Path(__file__).resolve().parent.parent / "perf"


def _resolve_executable(name: str) -> str | None:
    """Cross-platform PATH resolution. On Windows, `npm` is `npm.cmd`; bare
    `npm` does not work with subprocess.run(shell=False). shutil.which()
    returns the resolved path including the .cmd extension on Windows.
    """
    return shutil.which(name)


def _ensure_node_modules(perf_dir: Path) -> tuple[bool, str]:
    """Lazy `npm install` in the plugin's perf/ dir if node_modules missing.

    Returns (ok, diagnostic). Idempotent.
    """
    nm = perf_dir / "node_modules"
    if nm.is_dir() and (nm / "lighthouse").is_dir():
        return True, ""
    if not (perf_dir / "package.json").exists():
        return False, f"perf/package.json missing at {perf_dir}"
    npm = _resolve_executable("npm")
    if npm is None:
        return False, "npm not found on PATH (install Node.js / npm to use the performance gate)"
    sys.stderr.write(f"INFO: installing lighthouse npm dep in {perf_dir} (one-time)...\n")
    try:
        proc = subprocess.run(
            [npm, "install", "--silent", "--no-audit", "--no-fund"],
            cwd=str(perf_dir), shell=False, capture_output=True, text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"npm install failed: {exc}"
    if proc.returncode != 0:
        return False, f"npm install exit {proc.returncode}: {proc.stderr[-500:]}"
    return True, ""


def run_lighthouse(
    dev_url: str, project_root: Path, *, playwright_cwd: str = ""
) -> dict[str, Any]:
    """Run Lighthouse via Node script using project's Playwright Chromium.

    Returns parsed result dict (matches the lighthouse sub-block schema).
    `playwright_cwd` is the subdirectory (relative to project_root) where
    `node_modules/playwright` lives. Empty → project_root itself. Monorepo
    layouts (vite-hono client/, etc.) override via profile config.
    """
    # Validate scheme + warn on non-loopback. Raises ValueError on bad scheme.
    try:
        validate_dev_url(dev_url)
    except ValueError as exc:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE, f"invalid dev_url: {exc}")

    # Test seam — if active, short-circuit with fixture.
    if _test_seam_active():
        lhr = _load_fake_lhr()
        if lhr is None:
            return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                            "fake LHR fixture missing or empty")
        return _lh_from_lhr(lhr)

    # Preflight reachability (Review Finding 5).
    reachable, diag = preflight_dev_url(dev_url)
    if not reachable:
        return _lh_skip(SKIP_REASON_NO_DEV_URL, diag)

    # Lazy npm install in perf/ subdir.
    perf_dir = _perf_node_dir()
    ok, install_diag = _ensure_node_modules(perf_dir)
    if not ok:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE, install_diag)

    runner_script = perf_dir / "lighthouse-runner.mjs"
    if not runner_script.exists():
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                        f"lighthouse-runner.mjs missing at {runner_script}")

    node = _resolve_executable("node")
    if node is None:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE, "node not found on PATH")

    # cwd determines where Node resolves the `playwright` module. Defaults
    # to project_root; monorepo layouts override via profile config.
    if playwright_cwd:
        node_cwd = (project_root / playwright_cwd).resolve()
    else:
        node_cwd = project_root
    if not node_cwd.is_dir():
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                        f"playwright_cwd does not exist: {node_cwd}")

    # subprocess.run with shell=False — argv list, no shell-injection surface.
    try:
        proc = subprocess.run(
            [node, str(runner_script), dev_url],
            cwd=str(node_cwd), shell=False,
            capture_output=True, text=True, encoding="utf-8",
            timeout=LIGHTHOUSE_SUBPROCESS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                        f"lighthouse subprocess timed out after "
                        f"{LIGHTHOUSE_SUBPROCESS_TIMEOUT_S}s")
    except (OSError, FileNotFoundError) as exc:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE, f"node not available: {exc}")

    if proc.returncode != 0:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                        f"lighthouse exit {proc.returncode}: "
                        f"{(proc.stderr or proc.stdout)[-500:]}")

    try:
        lhr = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                        f"lighthouse JSON parse failed: {exc}")
    if "error" in lhr and "categories" not in lhr:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE,
                        f"lighthouse runner reported error: {lhr.get('error')}")

    return _lh_from_lhr(lhr)


def _lh_skip(reason: str, diag: str) -> dict[str, Any]:
    return {
        "ran": False, "skipped": True,
        "skip_reason": f"{reason}: {diag}" if diag else reason,
        "score": None, "lcp_ms": None,
        "score_passed": True, "lcp_passed": True,  # treat as pass for gate-purposes
    }


def _lh_from_lhr(lhr: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_lighthouse_report(lhr)
    if parsed["error"] and parsed["score"] is None:
        return _lh_skip(SKIP_REASON_LHCI_UNAVAILABLE, parsed["error"])
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "score": parsed["score"],
        "lcp_ms": parsed["lcp_ms"],
        # Budget comparison filled by main()
    }


# ── Main orchestration ───────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Performance budget check")
    parser.add_argument("--cwd", required=True, help="Project root")
    parser.add_argument("--profile-path", required=True, help="Path to profile JSON")
    parser.add_argument("--dev-url", default="", help="Dev server URL for Lighthouse")
    parser.add_argument("--gate", default="inherit",
                        choices=("warn", "block", "inherit"))
    args = parser.parse_args()

    started_at = time.monotonic()
    project_root = Path(args.cwd).resolve()

    # Load profile.testing.performance
    profile_perf: dict[str, Any] | None = None
    try:
        profile = json.loads(Path(args.profile_path).read_text(encoding="utf-8"))
        profile_perf = profile.get("testing", {}).get("performance")
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"WARNING: profile load failed: {exc}\n")

    # Load shipwright_test_config.json.performance (optional)
    test_config_perf: dict[str, Any] | None = None
    test_cfg_path = project_root / "shipwright_test_config.json"
    if test_cfg_path.exists():
        try:
            test_config_perf = json.loads(
                test_cfg_path.read_text(encoding="utf-8")
            ).get("performance")
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"WARNING: shipwright_test_config.json load failed: {exc}\n")

    cli_gate = None if args.gate == "inherit" else args.gate
    cfg = resolve_config(profile_perf, test_config_perf, cli_gate)

    # Profile-opts-out → emit skipped result, success, exit 0
    if not cfg.get("enabled"):
        result = {
            "success": True, "skipped": True,
            "skip_reason": cfg.get("skip_reason", SKIP_REASON_PROFILE_OPTS_OUT),
            "gate": cfg.get("gate", "warn"),
            "lighthouse": _lh_skip(SKIP_REASON_PROFILE_OPTS_OUT, ""),
            "bundle": {"ran": False, "skipped": True,
                       "skip_reason": SKIP_REASON_PROFILE_OPTS_OUT,
                       "total_kb_gz": 0.0, "files_measured": 0, "files": [],
                       "passed": True},
            "duration_seconds": round(time.monotonic() - started_at, 2),
        }
        print(json.dumps(result, indent=2))
        return 0

    # Lighthouse
    if args.dev_url:
        lh = run_lighthouse(
            args.dev_url, project_root,
            playwright_cwd=cfg["lighthouse"].get("playwright_cwd", ""),
        )
    else:
        lh = _lh_skip(SKIP_REASON_NO_DEV_URL, "no --dev-url passed")
    if lh.get("ran"):
        score_budget = cfg["lighthouse"]["min_score"]
        lcp_budget = cfg["lighthouse"]["lcp_max_ms"]
        lh["score_budget"] = score_budget
        lh["score_passed"] = (
            lh.get("score") is not None and lh["score"] >= score_budget
        )
        lh["lcp_budget_ms"] = lcp_budget
        lh["lcp_passed"] = (
            lh.get("lcp_ms") is not None and lh["lcp_ms"] <= lcp_budget
        )

    # Bundle
    build_dir_rel = cfg["bundle"].get("build_output_dir", "")
    if build_dir_rel:
        bundle = measure_bundle(project_root / build_dir_rel)
    else:
        bundle = {
            "ran": False, "skipped": True,
            "skip_reason": f"{SKIP_REASON_NO_BUILD_DIR}: bundle.build_output_dir empty",
            "total_kb_gz": 0.0, "files_measured": 0, "files": [],
            "passed": True,
        }
    if bundle.get("ran") and not bundle.get("skipped"):
        budget = cfg["bundle"]["max_kb_gz"]
        bundle["budget_kb_gz"] = budget
        bundle["passed"] = bundle["total_kb_gz"] <= budget

    results = {"lighthouse": lh, "bundle": bundle}
    success = evaluate_gate(results, cfg["gate"])

    out = {
        "success": success,
        "skipped": False,
        "skip_reason": "",
        "gate": cfg["gate"],
        **results,
        "duration_seconds": round(time.monotonic() - started_at, 2),
    }
    print(json.dumps(out, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
