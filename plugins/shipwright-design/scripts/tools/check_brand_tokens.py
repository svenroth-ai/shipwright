"""Check a brand token override against the Untitled UI token contract, with a fix suggestion for each weak colour pair.

    uv run check_brand_tokens.py --base warm --overrides brand.css     # shipped set + the brand's overrides (they win)
    uv run check_brand_tokens.py --tokens full-set.css                 # one complete token file, no base

Exit 0: every contract rule holds. Exit 1: failures, one line each, with the nearest passing colour where one exists.
Exit 2: a named file does not exist.
The tests in tests/test_untitled_ui_kit.py run the same rules over the shipped sets (CONTRAST_PAIRS, check_css()).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "skills" / "design" / "kit" / "untitled-ui"

# (foreground, background, minimum): 7.0 for secondary text (readable, WCAG AAA), 4.5 for other text (AA), 3.0 for controls and focus
CONTRAST_PAIRS = [
    ("text", "bg", 4.5), ("text", "surface", 4.5), ("muted", "bg", 7.0), ("muted", "surface", 7.0),
    ("muted", "table-header", 7.0), ("on-primary", "primary", 4.5), ("on-primary", "primary-hover", 4.5),
    ("primary", "surface", 4.5), ("primary", "bg", 4.5), ("on-primary", "error", 4.5),
    ("success", "success-bg", 4.5), ("warning", "warning-bg", 4.5), ("error", "error-bg", 4.5), ("info", "info-bg", 4.5),
    ("success", "surface", 4.5), ("warning", "surface", 4.5), ("error", "surface", 4.5),
    ("muted", "hover", 7.0), ("text", "hover", 4.5), ("muted", "primary-soft", 7.0), ("text", "primary-soft", 4.5), ("muted", "border", 7.0), ("text", "border", 4.5), ("border-strong", "surface", 3.0), ("border-strong", "bg", 3.0), ("focus", "surface", 3.0), ("focus", "bg", 3.0), ("info", "surface", 4.5), ("primary", "primary-soft", 3.0), ("text", "table-header", 4.5),
]
# colours that carry no contrast rule but must still be defined
OTHER_COLOURS = ("secondary", "primary-ring", "info-bg", "success-bg", "warning-bg", "error-bg")
# which side of a weak pair a suggestion moves: the foreground, except where the fill is the chosen colour
MOVES_BACKGROUND = {("on-primary", "primary"), ("on-primary", "primary-hover"), ("on-primary", "error")}


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _declared(css: str, prefix: str) -> dict[str, str]:
    """`--<prefix>-<name>: value` declarations; a later one wins, which is how an override follows its base set."""
    return {k: v.strip() for k, v in re.findall(rf"--{prefix}-([\w-]+):\s*([^;}}]+)", css)}


def _hex6(value: str) -> str | None:
    """A solid hex colour as `#rrggbb` (a 3-digit `#abc` is expanded), else None."""
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value)
    if not m:
        return None
    h = m.group(1).lower()
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def parse_colours(css: str) -> dict[str, str]:
    return {k: h for k, v in _declared(css, "color").items() if k != "overlay" and (h := _hex6(v))}


def parse_sizes(css: str) -> dict[str, int]:
    return {k: int(m.group(1)) for k, v in _declared(css, "font-size").items() if k in ("base", "sm") and (m := re.fullmatch(r"(\d+)px", v))}


def unreadable_values(css: str) -> list[str]:
    """Values the checker cannot judge (rgb(), hsl(), var(), 8-digit hex, a non-px base size): reported, never skipped."""
    bad = [f"--color-{k}: '{v}' is not a solid hex colour (#rrggbb)" for k, v in _declared(css, "color").items() if k != "overlay" and not _hex6(v)]
    bad += [f"--font-size-{k}: '{v}' is not a px size" for k, v in _declared(css, "font-size").items() if k in ("base", "sm") and not re.fullmatch(r"\d+px", v)]
    return bad


def _mix(colour: str, target: str, amount: float) -> str:
    c, t = colour.lstrip("#"), target.lstrip("#")
    return "#" + "".join(f"{round(int(c[i:i+2], 16) + (int(t[i:i+2], 16) - int(c[i:i+2], 16)) * amount):02x}" for i in (0, 2, 4))


def nearest_passing(moving: str, fixed: str, need: float) -> str | None:
    """Move `moving` toward whichever of black or white lifts the contrast against `fixed`, in 1% steps, until it passes."""
    target = max(("#000000", "#ffffff"), key=lambda t: contrast(t, fixed))
    for step in range(1, 101):
        candidate = _mix(moving, target, step / 100)
        if contrast(candidate, fixed) >= need:
            return candidate
    return None


def check(colours: dict[str, str], sizes: dict[str, int] | None = None) -> list[str]:
    """Every contract rule the tests enforce; one line per failure, a suggestion appended where one exists."""
    failures = [f"missing --color-{n}" for n in sorted({n for p in CONTRAST_PAIRS for n in p[:2]} | set(OTHER_COLOURS)) if n not in colours]
    if failures:
        return failures
    for fg, bg, need in CONTRAST_PAIRS:
        ratio = contrast(colours[fg], colours[bg])
        if ratio >= need:
            continue
        move, fixed = (bg, fg) if (fg, bg) in MOVES_BACKGROUND else (fg, bg)
        fix = nearest_passing(colours[move], colours[fixed], need)
        hint = f"; try --color-{move}: {fix}" if fix else ""
        failures.append(f"{fg} {colours[fg]} on {bg} {colours[bg]}: {ratio:.2f} < {need}{hint}")
    if luminance(colours["primary-hover"]) >= luminance(colours["primary"]):
        failures.append(f"primary-hover {colours['primary-hover']} must be darker than primary {colours['primary']}")
    if sizes is not None:
        failures += [f"missing --font-size-{n}" for n in ("base", "sm") if n not in sizes]
        if sizes.get("base", 16) < 16 or sizes.get("sm", 14) < 14:
            failures.append(f"font sizes below the minimum (base >= 16px, sm >= 14px): {sizes}")
    return failures


def check_css(css: str) -> list[str]:
    """`check()` over a whole stylesheet, with every value it cannot read reported first."""
    return unreadable_values(css) + check(parse_colours(css), parse_sizes(css))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", choices=sorted(p.stem for p in (KIT / "tokens").glob("*.css")), help="shipped token set to start from")
    ap.add_argument("--overrides", type=Path, help="CSS with the brand's --color-* / --font-size-* values; they win over --base")
    ap.add_argument("--tokens", type=Path, help="one complete token CSS file (instead of --base / --overrides)")
    args = ap.parse_args(argv)
    if not (args.tokens or args.base):
        ap.error("give --base (optionally with --overrides) or --tokens")
    parts = [args.tokens] if args.tokens else [KIT / "tokens" / f"{args.base}.css"] + ([args.overrides] if args.overrides else [])
    missing = [p for p in parts if not p.is_file()]
    if missing:
        print("not found:", ", ".join(map(str, missing)), file=sys.stderr)
        return 2
    failures = check_css("\n".join(p.read_text(encoding="utf-8") for p in parts))
    for line in failures:
        print(line)
    print(f"FAIL: {len(failures)} problem(s)" if failures else "OK: all contract rules hold")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
