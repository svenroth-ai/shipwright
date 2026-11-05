"""Rules an autonomous run applies instead of asking a person (e2e run 22).

Run 22 put six questions to a person that a rule can answer. Four of them need a
deterministic check, and those checks live here; ``tools/record_autonomous_decision.py``
writes the outcome into the decision log (and, for a difference the built app will show,
into ``.shipwright/designs/known-differences.md``). Every rule applies only to an
autonomous run (:func:`is_autonomous_run`: a brief package governs it, or autonomy is
``autonomous``/``unattended``); an interactive run is unchanged and still asks.

* **Approved links** (:func:`standalone_split`) -- an external ``<a href>`` the approved
  package mockup already carries (Open thread, a posted-comment link) is approved
  functionality, not a loaded asset. The design ``standalone`` gate keeps it instead of
  failing; every other external reference still fails, exactly as before.
* **Explicit brief value** (:func:`brief_states`) -- a brief value wins over plan text and
  over screens that do not show it, but only a value the brief really states: the quote
  must occur in the package's ``brief.md``.
* **Hard requirement over a visible extra** -- the ranking is a reading (reviewer and
  builder); the recorder only refuses a record without measurements (:func:`has_measurements`).
* **Declared dev tooling** (:func:`dev_tooling_verdict`) -- an install of tooling the project
  already declares (its ``package.json``/``pyproject.toml``, or the stack profile's test
  framework) may run; anything else stays a question.
"""

from __future__ import annotations

import json
import re
import shlex
from html.parser import HTMLParser
from pathlib import Path

try:
    from .design_gate_html import ALLOWED_EXTERNAL_HOSTS, external_host
    from .plan_design_check import is_autonomous_design_run as is_autonomous_run
except ImportError:  # loaded top-level (check-design-gates.py puts shared/scripts/lib on sys.path)
    from design_gate_html import ALLOWED_EXTERNAL_HOSTS, external_host
    from plan_design_check import is_autonomous_design_run as is_autonomous_run

__all__ = ["KNOWN_DIFFERENCES_REL", "append_known_difference", "approved_package_links", "brief_states",
           "dev_tooling_verdict", "has_measurements", "known_difference_exists", "is_autonomous_run", "standalone_findings", "standalone_split"]

KNOWN_DIFFERENCES_REL = ".shipwright/designs/known-differences.md"
_DESIGNS_REL = ".shipwright/designs"
_WS = re.compile(r"\s+")
_KD_RE = re.compile(r"^## KD-(\d+)\b", re.M)
_MEASURE_RE = re.compile(r"\d+(?:\.\d+)?\s*px\b", re.I)
_SHELL_META = re.compile(r"[;&|`$<>\n\\]")
_BROWSERS = {"chromium", "firefox", "webkit", "chrome", "msedge", "chromium-headless-shell"}
_PW_PACKAGES = ("@playwright/test", "playwright")
_JS_TOOLS = {"npm": ("install", "i", "ci"), "pnpm": ("install", "i"), "yarn": ("install",)}
#: Allow-lists, never deny-lists: any other flag (global, registry, userconfig, upgrade, directory) is a question.
_JS_FLAGS = {"-D", "--save-dev", "-E", "--save-exact", "--no-audit", "--no-fund", "--ignore-scripts",
             "--prefer-offline", "--frozen-lockfile"}
_UV_FLAGS = re.compile(r"^(--frozen|--locked|--all-extras|--dev|--all-groups|--extra=[\w.-]+|--group=[\w.-]+)$")
_UV_VALUE_FLAGS = {"--extra", "--group"}
_UV_VALUE = re.compile(r"^[\w.-]+$")
_KD_HEADER = ("# Known differences: built app and approved screens\n\n"
              "Written by autonomous runs (`record_autonomous_decision.py`), one entry per rule decision. "
              "It waives nothing: `screenshot_check.py` does not read this file.\n")


class _Tags(HTMLParser):
    """``(tag, attrs)`` per start tag; a comment body is scanned again (fails closed, as gate #6)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        seen: dict[str, str] = {}
        for name, value in attrs:
            seen.setdefault(name.lower(), value or "")
        self.tags.append((tag.lower(), seen))

    def handle_comment(self, data: str) -> None:
        self.tags.extend(_tags(data))


def _tags(html: str) -> list[tuple[str, dict[str, str]]]:
    parser = _Tags()
    parser.feed(html)
    return parser.tags


def _external(raw: str) -> bool:
    host = external_host(raw)
    return host is not None and host not in ALLOWED_EXTERNAL_HOSTS


def standalone_split(html: str, approved: set[str]) -> tuple[list[str], list[str]]:
    """``(violations, kept)``. With ``approved`` empty, ``violations`` equals gate #6's list."""
    violations, kept = [], []
    for tag, attrs in _tags(html):
        for name in ("src", "href"):
            raw = attrs.get(name)
            if not raw or not _external(raw):
                continue
            (kept if tag == "a" and name == "href" and raw.strip() in approved else violations).append(raw)
    return violations, kept


def approved_package_links(uploads_dir: Path) -> set[str]:
    """External ``<a href>`` values in the approved package mockups (``.shipwright/designs/uploads``)."""
    links: set[str] = set()
    for path in sorted(Path(uploads_dir).glob("*.html")):
        try:
            html = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        links |= {a["href"].strip() for tag, a in _tags(html) if tag == "a" and a.get("href") and _external(a["href"])}
    return links


def standalone_findings(project_root: Path, files: list[str]) -> tuple[list[str], list[str]]:
    """Gate #6 over ``files`` (relative to ``.shipwright/designs``): ``(problems, kept)``.

    Approved links are kept only in an autonomous run whose brief package was applied
    (``brief-package-applied.json``: the ``uploads`` gate holds them byte-identical to the package).
    """
    designs = Path(project_root) / _DESIGNS_REL
    approved: set[str] = set()
    if is_autonomous_run(project_root) and (designs / "brief-package-applied.json").is_file():
        approved = approved_package_links(designs / "uploads")
    problems, kept = [], []
    for rel in files:
        try:
            html = (designs / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            html = ""
        violations, ok = standalone_split(html, approved)
        problems += [f"{rel}: external reference {v}" for v in violations]
        kept += [f"{rel}: approved package link {k}" for k in ok]
    return problems, kept


def _norm(text: str) -> str:
    return _WS.sub(" ", text.replace("’", "'")).strip().lower()


def _brief_text(project_root: Path) -> str | None:
    """The package's ``brief.md`` (run config ``brief_dir``: project-relative, inside the project)."""
    root = Path(project_root).resolve()
    try:
        cfg = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))
        raw = cfg.get("brief_dir") if isinstance(cfg, dict) else None
        rel = raw.replace("\\", "/") if isinstance(raw, str) else ""
        if not rel.strip() or Path(rel).is_absolute() or ".." in rel.split("/"):
            return None
        brief = (root / rel / "brief.md").resolve()
        if not brief.is_relative_to(root):
            return None
        return brief.read_text(encoding="utf-8-sig", errors="ignore")
    except (OSError, ValueError, AttributeError):
        return None


def brief_states(project_root: Path, quote: str) -> bool:
    """True when ``quote`` -- a clause (at least 20 characters and 3 words), not a fragment such as
    "is shown" -- occurs in the package's brief.md, case and spacing aside."""
    wanted = _norm(quote.strip().strip('"').strip("'"))
    text = _brief_text(project_root)
    return len(wanted) >= 20 and len(wanted.split()) >= 3 and text is not None and wanted in _norm(text)


def has_measurements(text: str) -> bool:
    """A record of a hard-requirement decision names at least one measured width (``NNN px``)."""
    return bool(_MEASURE_RE.search(text or ""))


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _npm_declared(root: Path) -> set[str] | None:
    pkg = root / "package.json"
    if not pkg.is_file():
        return None
    data = _json(pkg)
    return {name for key in ("dependencies", "devDependencies") if isinstance(data.get(key), dict)
            for name in data[key]}


def _pkg_name(spec: str) -> str | None:
    """The bare package name; ``None`` for ``name@<anything>`` (a version, alias, git, file or URL spec
    would change what package.json declares, so it is never "already declared")."""
    return None if spec.find("@", 1) > 0 else spec


def _uv_args_ok(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        if args[i] in _UV_VALUE_FLAGS and i + 1 < len(args) and _UV_VALUE.match(args[i + 1]):
            i += 2
            continue
        if not _UV_FLAGS.match(args[i]):
            return False
        i += 1
    return True


def dev_tooling_verdict(command: str, project_root: Path, profile: dict | None = None) -> tuple[bool, str]:
    """``(may_install, why)`` for ONE install command an autonomous run wants to run.

    Allowed: ``npm|pnpm|yarn install`` (and ``npm ci``) of what ``package.json`` declares, optionally naming
    only packages it already declares; ``npx playwright install [browser...]`` when Playwright is declared
    (manifest or the profile's ``testing.e2e.framework``); ``uv sync`` with a ``pyproject.toml``. A global
    install, another registry, ``--with-deps`` (system packages), shell syntax or any other command: ask.
    """
    root = Path(project_root)
    if _SHELL_META.search(command or ""):
        return False, "not a single plain command (shell syntax)"
    try:
        tokens = shlex.split(command or "")
    except ValueError:
        return False, "not a parseable command"
    declared = _npm_declared(root)
    if len(tokens) >= 2 and tokens[0] in _JS_TOOLS and tokens[1] in _JS_TOOLS[tokens[0]]:
        if declared is None:
            return False, "no package.json declares anything to install"
        flags = [t for t in tokens[2:] if t.startswith("-")]
        if any(f not in _JS_FLAGS for f in flags):
            return False, f"flag not allowed for a declared install: {' '.join(f for f in flags if f not in _JS_FLAGS)}"
        specs = [t for t in tokens[2:] if not t.startswith("-")]
        missing = sorted(t for t in specs if _pkg_name(t) not in declared)
        if missing:
            return False, f"not declared in package.json: {', '.join(missing)}"
        return True, "installs only what package.json already declares"
    if tokens[:3] == ["npx", "playwright", "install"]:
        extra = [t for t in tokens[3:] if t.lower() not in _BROWSERS]
        if extra:
            return False, f"not a browser download: {' '.join(extra)}"
        framework = str(((profile or {}).get("testing") or {}).get("e2e", {}).get("framework", ""))
        if (declared and any(p in declared for p in _PW_PACKAGES)) or framework in _PW_PACKAGES:
            return True, "Playwright is declared (package.json or the stack profile's e2e framework)"
        return False, "Playwright is declared neither in package.json nor in the stack profile"
    if tokens[:2] == ["uv", "sync"]:
        if not (root / "pyproject.toml").is_file():
            return False, "no pyproject.toml declares anything to sync"
        if not _uv_args_ok(tokens[2:]):
            return False, f"argument not allowed for a declared sync: {' '.join(tokens[2:])}"
        return True, "installs only what pyproject.toml already declares"
    return False, "not an install of declared dev tooling (npm/pnpm/yarn install, npx playwright install, uv sync)"


def known_difference_exists(project_root: Path, title: str) -> bool:
    """A ``## KD-NN: <title>`` entry already exists (a resumed or repeated call records nothing twice)."""
    try:
        text = (Path(project_root) / KNOWN_DIFFERENCES_REL).read_text(encoding="utf-8")
    except OSError:
        return False
    want = _norm(title)
    return any(_norm(m.group(1)) == want for m in re.finditer(r"^## KD-\d+:\s*(.+)$", text, re.M))


def append_known_difference(project_root: Path, title: str, fields: list[tuple[str, str]]) -> str:
    """Append ``## KD-NN: <title>`` with ``- **field:** value`` lines; returns ``KD-NN``."""
    path = Path(project_root) / KNOWN_DIFFERENCES_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = _KD_HEADER
    number = max((int(n) for n in _KD_RE.findall(text)), default=0) + 1
    kd = f"KD-{number:02d}"
    body = "\n".join(f"- **{k}:** {_WS.sub(' ', v).strip()}" for k, v in fields if v and v.strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + f"\n\n## {kd}: {_WS.sub(' ', title).strip()}\n\n{body}\n", encoding="utf-8")
    return kd
