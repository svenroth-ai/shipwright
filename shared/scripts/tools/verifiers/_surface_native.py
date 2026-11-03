"""Which UI is native, and which staged results can vouch for it (``surface=native``, #989).

A native-only app (Expo / React Native, no browser build) has no Playwright report to stage,
so ``surface=web`` can never pass for it. ``native`` takes the evidence such an app really
has - Jest results - but only for UI that provably lies in a native package, so it cannot be
used to skip the browser run for a web app:

* every touched UI path must have a nearest ``package.json`` (at the verified commit) that
  depends on ``react-native`` or ``expo`` and on no web framework. ``react-dom`` counts as
  one only without ``react-native-web``: the stock ``create-expo-app`` template carries both.
  Malformed or non-object manifests are not native; a package that is not native at the
  merge-base is refused too (the diff cannot rewrite the declaration it is judged by),
  unless the package is new in the diff;
* a file type that cannot run natively (``*.web.tsx``, ``.html``, ``.vue``, ...) is refused;
* a result counts only when it comes from a JS/TS test file under a touched native package
  (path-aware, ``..`` collapsed), and every touched package needs at least one passing one.

Known limits: the nearest manifest decides (no workspace-root hoisting); Jest JSON paths are absolute, so
they line up only on the machine that ran the tests; the first iterate that adds a native app under a root
manifest that itself counts as web (a Next root, or a workspace hoisting react-dom / vite) is refused and
goes through the operator's accepted red once; a NEW file under a manifest this diff adds is judged by
that manifest unless a web package owned the location at the merge-base (existing files are fully protected).
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from ._surface_detect import _TEMPLATE_SUFFIXES
from .git_helpers import _run_git

__all__ = ["NativeScope", "native_packages"]

NATIVE_DEPENDENCIES = frozenset({"react-native", "expo"})
#: A web framework or shell: the package is not (only) native.
WEB_DEPENDENCIES = frozenset({
    "next", "vite", "gatsby", "electron", "preact", "vue", "svelte", "astro", "solid-js", "@angular/core",
    "nuxt", "react-scripts", "webpack", "parcel", "@expo/webpack-config", "@tanstack/start", "@tanstack/react-start", "esbuild", "rollup", "lit",
    "waku", "umi", "@ionic/react", "@capacitor/core", "@rsbuild/core", "@rspack/core", "@farmfe/core",
})
WEB_DEPENDENCY_PREFIXES = ("@remix-run/", "@sveltejs/", "@nuxt/", "@vitejs/", "@react-router/", "@modern-js/",
                           "@tauri-apps/", "@storybook/")
REACT_DOM, REACT_NATIVE_WEB = "react-dom", "react-native-web"
DEPENDENCY_FIELDS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
#: UI files that only a browser or a server can render (the detector's server-template list + browser-only types).
WEB_ONLY_SUFFIXES = tuple(sorted({".html", ".vue", ".svelte", ".astro"} | set(_TEMPLATE_SUFFIXES)))
WEB_ONLY_PLATFORM = (".web.ts", ".web.tsx", ".web.js", ".web.jsx", ".web.mjs", ".web.cjs")
#: Expo Router renders these for the web/static export only.
WEB_ONLY_NAMES = frozenset({f"+html.{e}" for e in ("tsx", "ts", "jsx", "js", "mjs", "cjs")})
#: Expo Router API routes are server code: Jest on the device runtime does not exercise them.
WEB_ONLY_INFIXES = ("+api.",)
#: What a native test result may be: Jest runs JS/TS only, so a Python JUnit never qualifies.
TEST_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
#: A path that is not project-relative: POSIX-absolute, a Windows drive, or UNC.
#: A Jest test file by name or folder; a config or helper script is no evidence.
_TESTISH = re.compile(r"(\.(test|spec)\.|(^|/)__tests__/)")
_FOREIGN_PATH = re.compile(r"^(/|[A-Za-z]:)")


def _manifest(project_root: Path, rev: str, directory: str, cache: dict) -> tuple[bool, dict | None]:
    """``(exists, parsed)`` of ``<directory>/package.json`` at ``rev``; ``parsed`` is ``None`` when unusable."""
    key = (rev, directory)
    if key not in cache:
        rc, out, _ = _run_git(project_root, "show", f"{rev}:{posixpath.join(directory, 'package.json')}", timeout=15.0)
        parsed = None
        if rc == 0:
            try:
                data = json.loads(out)
                parsed = data if isinstance(data, dict) else None
            except ValueError:
                parsed = None
        cache[key] = (rc == 0, parsed)
    return cache[key]


def _deps(manifest: dict) -> set[str]:
    names: set[str] = set()
    for field in DEPENDENCY_FIELDS:
        section = manifest.get(field)
        if isinstance(section, dict):
            names.update(str(name) for name in section)
    return names


def is_web_manifest(manifest: dict | None) -> bool:
    """A browser package: a web framework, or ``react-dom`` unless it comes with ``react-native-web`` AND ``expo``
    (the stock Expo template; any other react-dom + react-native-web package is a browser target). Unusable = web (fail closed)."""
    if not isinstance(manifest, dict):
        return True
    deps = _deps(manifest)
    return bool(WEB_DEPENDENCIES & deps or any(d.startswith(WEB_DEPENDENCY_PREFIXES) for d in deps)
                or (REACT_DOM in deps and not (REACT_NATIVE_WEB in deps and "expo" in deps)))


def is_native_manifest(manifest: dict | None) -> bool:
    return isinstance(manifest, dict) and bool(NATIVE_DEPENDENCIES & _deps(manifest)) and not is_web_manifest(manifest)


def _exists_at(project_root: Path, rev: str, path: str, cache: dict) -> bool:
    key = ("file", rev, path)
    if key not in cache:
        cache[key] = _run_git(project_root, "cat-file", "-e", f"{rev}:{path}", timeout=15.0)[0] == 0
    return cache[key]


def _nearest_package(project_root: Path, commit: str, path: str, cache: dict) -> tuple[str, dict | None] | None:
    directory = posixpath.dirname(path)
    while True:
        exists, parsed = _manifest(project_root, commit, directory, cache)
        if exists:
            return directory, parsed
        if not directory:
            return None
        directory = posixpath.dirname(directory)


def native_packages(project_root: Path, commit: str, base: str, ui_paths: list[str]) -> tuple[NativeScope | None, str | None]:
    """``(scope, problem)``: the native packages every touched UI path lies in, or why ``native`` is refused.

    A path is judged by its nearest package at the verified commit AND at the merge-base, because
    the diff must not rewrite the declaration it is judged by (add a nested ``package.json`` or
    delete a web one, and a web file would read as native):

    * a file that existed at the merge-base needs a base-side package that is the same one and native;
    * a NEW file is refused only when the package that owned its location at the merge-base is a web
      package (a new Expo app in a monorepo whose workspace root is a bare manifest is the normal case).
    """
    if base and base == commit:
        return None, "the verified commit is the merge-base, so there is no earlier declaration to hold this diff to"
    cache: dict = {}
    roots: set[str] = set()
    for path in ui_paths:
        lower = path.lower()
        if lower.endswith(WEB_ONLY_SUFFIXES + WEB_ONLY_PLATFORM) or posixpath.basename(lower) in WEB_ONLY_NAMES or any(i in posixpath.basename(lower) for i in WEB_ONLY_INFIXES):
            return None, f"{path} is a web-only file that cannot run natively"
        found = _nearest_package(Path(project_root), commit, path, cache)
        if found is None:
            return None, f"{path} has no package.json above it at the verified commit, so it is not in a native package"
        directory, manifest = found
        where = f"{directory or '.'}/package.json"
        if not is_native_manifest(manifest):
            return None, (f"{path} is not in a native package ({where} lacks react-native / expo, carries a web "
                        "framework, or lists react-dom without react-native-web)")
        if base:
            before = _nearest_package(Path(project_root), base, path, cache)
            if _exists_at(Path(project_root), base, path, cache):
                owned = before is not None and before[0] == directory and is_native_manifest(before[1])
                had = f"its package at the merge-base ({before[0] or '.'}/package.json)" if before else "no package.json above it at the merge-base"
            else:
                owned = before is None or not is_web_manifest(before[1])
                had = f"the web package that owned this location at the merge-base ({before[0] or '.'}/package.json)" if before else ""
            if not owned:
                return None, (f"{path}: {had} is not a native package declaring this file as {where} now, and this diff "
                            "cannot rewrite the declaration it is judged by")
        roots.add(directory)
    ordered = sorted(roots)
    consumer = _consumer_problem(Path(project_root), commit, ordered, cache)
    if consumer:
        return None, consumer
    scope = _tree_scope(Path(project_root), commit, ordered)
    return (scope, None) if scope else (None, "git cannot list the files of the verified commit")


@dataclass(frozen=True)
class NativeScope:
    """The native packages ``surface=native`` was granted for, and which staged results belong to them.

    ``roots`` are the touched packages' directories (``""`` = the repo root). ``nested`` are other
    packages that sit INSIDE a root: their tests belong to them, not to the root that contains them.
    A repo-root package therefore owns every project-relative JS/TS test result that no nested
    package claims - that is its meaning, not an oversight.
    """

    roots: tuple[str, ...]
    nested: tuple[str, ...] = ()
    files: frozenset[str] = frozenset()  # JS/TS files tracked at the verified commit under a root: a result must name one

    def owner(self, tid: str) -> str | None:
        """The touched package a JS/TS test result belongs to (``..`` collapsed, whole path segments), else ``None``."""
        path = posixpath.normpath(tid.split("::", 1)[0].replace("\\", "/"))
        if path.startswith("../") or path == ".." or _FOREIGN_PATH.match(path) or not path.lower().endswith(TEST_SUFFIXES):
            return None
        inside = [r for r in self.roots if not r or path.startswith(r + "/")]
        if not inside:
            return None
        best = max(inside, key=len)
        if path not in self.files or any(path.startswith(n + "/") and len(n) > len(best) for n in self.nested):
            return None
        return best

    def contains(self, path: str) -> bool:
        """``path`` lies in a touched native package (not in a package nested inside it)."""
        path = posixpath.normpath(path.replace("\\", "/"))
        inside = [r for r in self.roots if not r or path.startswith(r + "/")]
        best = max(inside, key=len) if inside else None
        return best is not None and not any(path.startswith(n + "/") and len(n) > len(best) for n in self.nested)

    def uncovered(self, passing: list[str]) -> str | None:
        """The first touched package none of the ``passing`` result ids belongs to, else ``None``."""
        owners = {self.owner(tid) for tid in passing}
        return next((root or "." for root in self.roots if root not in owners), None)


def _tree_scope(project_root: Path, commit: str, roots: list[str]) -> NativeScope | None:
    """The scope for ``roots`` from one listing of ``commit``'s files; ``None`` when git cannot list them."""
    rc, out, _ = _run_git(project_root, "ls-tree", "-r", "--name-only", commit, timeout=60.0)
    if rc != 0:
        return None
    tracked = [p for p in out.splitlines() if "node_modules" not in p.split("/")]
    dirs = {posixpath.dirname(p) for p in tracked if posixpath.basename(p) == "package.json"}
    nested = tuple(sorted(d for d in dirs if d not in roots and any(not r or d.startswith(r + "/") for r in roots)))
    files = frozenset(p for p in tracked if p.lower().endswith(TEST_SUFFIXES) and _TESTISH.search(p.lower()) and any(not r or p.startswith(r + "/") for r in roots))
    return NativeScope(tuple(roots), nested, files)


def _consumer_problem(project_root: Path, commit: str, roots: list[str], cache: dict) -> str | None:
    """A web package at ``commit`` that depends on a touched native package renders its screens in a browser."""
    for root in roots:
        name = (_manifest(project_root, commit, root, cache)[1] or {}).get("name")
        if not isinstance(name, str) or not name:
            continue
        rc, out, _ = _run_git(project_root, "grep", "-l", "-F", "-e", f'"{name}"', commit, "--", "*package.json", timeout=60.0)
        for line in out.splitlines() if rc == 0 else ():
            path = line.split(":", 1)[-1]
            directory = posixpath.dirname(path)
            if directory == root or "node_modules" in path.split("/"):
                continue
            other = _manifest(project_root, commit, directory, cache)[1]
            if isinstance(other, dict) and is_web_manifest(other) and name in _deps(other):
                return f"{path} (a web package) depends on {name!r}, so the screens of {root or '.'}/package.json also render in a browser"
    return None
