"""Compose the Untitled UI kit examples: page shell + token set + kit.css + a fragment, as standalone HTML.

    uv run build_kit_examples.py            # write kit/untitled-ui/examples/<fragment>-<tokens>.html
    uv run build_kit_examples.py --check    # exit 1 when a committed example differs from what the kit builds

The same composition is what the design phase does for a screen: shell, one token set, the kit, the screen body.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "skills" / "design" / "kit" / "untitled-ui"
FONTS = {
    "warm": "Libre+Baskerville:wght@400;700",
    "clean": "Inter:wght@400;500;600;700",
    "bold": "Plus+Jakarta+Sans:wght@400;500;600;700",
}
SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family={font}&display=swap" rel="stylesheet">
<style>
{tokens}
{kit}
</style>
</head>
<body>
{body}</body>
</html>
"""


def _read(kit: Path, rel: str) -> str:
    return (kit / rel).read_text(encoding="utf-8")


def compose(fragment: str, tokens: str, kit: Path = KIT) -> str:
    if tokens not in FONTS:
        raise KeyError(f"token set '{tokens}' has no entry in FONTS; add its Google Fonts family there")
    return SHELL.format(
        title=f"{fragment} ({tokens} tokens)",
        font=FONTS[tokens],
        tokens=_read(kit, f"tokens/{tokens}.css").rstrip(),
        kit=_read(kit, "kit.css").rstrip(),
        body=_read(kit, f"fragments/{fragment}.html"),
    )


def targets(kit: Path = KIT) -> dict[Path, str]:
    token_sets = sorted(p.stem for p in (kit / "tokens").glob("*.css"))
    return {
        kit / "examples" / f"{frag.stem}-{tok}.html": compose(frag.stem, tok, kit)
        for frag in sorted((kit / "fragments").glob("*.html"))
        for tok in token_sets
    }


def main(argv: list[str] | None = None, kit: Path = KIT) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    check = ap.parse_args(argv).check
    built = targets(kit)
    stale = []
    if check:
        for path, html in built.items():
            if not path.exists() or path.read_text(encoding="utf-8") != html:
                stale.append(path.name)
        stale += [p.name for p in sorted((kit / "examples").glob("*.html")) if p not in built]
    else:
        for path, html in built.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8", newline="\n")
    if stale:
        print("stale kit examples (run build_kit_examples.py):", ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
