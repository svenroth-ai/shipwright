"""Browser verify — run the TypeScript browser-verify helper and parse results.

Usage from SKILL.md:
    uv run {shared_root}/scripts/playwright_setup.py --cwd {project_root}
    uv run {shared_root}/scripts/browser_verify.py --cwd {project_root} [--url http://localhost:3000]

Returns JSON:
    {
        "success": true/false,
        "screenshot": "e2e/screenshots/browser-verify.png",
        "console_errors": [...],
        "title": "My App",
        "dom_snippet": "..."
    }
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_browser_verify(
    cwd: Path,
    url: str = "http://localhost:3000",
    timeout: int = 60,
) -> dict:
    """Run browser-verify.ts in the target project and return parsed results."""
    verify_script = cwd / "e2e" / "browser-verify.ts"
    result_file = cwd / "browser-verify-result.json"

    if not verify_script.exists():
        return {
            "success": False,
            "error": f"browser-verify.ts not found at {verify_script}. Run playwright_setup.py first.",
        }

    # Run the TypeScript helper
    try:
        proc = subprocess.run(
            ["npx", "tsx", str(verify_script), "--url", url, "--output", str(result_file)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Browser verify timed out after {timeout}s",
        }
    except OSError as e:
        return {
            "success": False,
            "error": f"Failed to run browser-verify.ts: {e}",
        }

    # Parse result file (preferred over stdout — more reliable)
    if result_file.exists():
        try:
            return json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # Fallback: parse stdout
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"Could not parse browser-verify output",
            "stdout": proc.stdout[:2000] if proc.stdout else "",
            "stderr": proc.stderr[:2000] if proc.stderr else "",
            "returncode": proc.returncode,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run browser verify check")
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument("--url", default="http://localhost:3000", help="URL to verify")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    result = run_browser_verify(cwd, args.url, args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
