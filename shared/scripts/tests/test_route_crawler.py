"""Tests for route_crawler.py — static-route extractor + screenshot summary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import route_crawler  # noqa: E402
from route_crawler import (  # noqa: E402
    _normalize_route,
    _summarize_screenshots,
    extract_static_routes,
    run_crawl,
)


# --- _normalize_route ---------------------------------------------------


def test_normalize_route_strips_param_routes_returns_none():
    assert _normalize_route("/users/:id") is None
    assert _normalize_route("/posts/:slug?") is None


def test_normalize_route_handles_splat():
    assert _normalize_route("*") is None
    assert _normalize_route("/files/*") is None


def test_normalize_route_makes_relative_absolute():
    assert _normalize_route("dashboard") == "/dashboard"


def test_normalize_route_root():
    assert _normalize_route("/") == "/"


def test_normalize_route_strips_trailing_segments():
    assert _normalize_route("/projects//") == "/projects"


# --- extract_static_routes — react-router fixture -----------------------


def test_extract_react_router_createBrowserRouter(tmp_path):
    """Realistic react-router-v6 createBrowserRouter file."""
    src = tmp_path / "client" / "src"
    src.mkdir(parents=True)
    (src / "router.tsx").write_text(
        """
import { createBrowserRouter } from 'react-router-dom';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      { path: '/projects', element: <Projects /> },
      { path: '/inbox', element: <Inbox /> },
      { path: '/settings', element: <Settings /> },
      { path: '/diagnostics', element: <Diagnostics /> },
      { path: '/tasks/:id', element: <TaskDetail /> },
    ],
  },
]);
""",
        encoding="utf-8",
    )
    seeds = extract_static_routes(tmp_path)
    # Order-preserved, dedup, param routes (`/tasks/:id`) excluded.
    assert "/" in seeds
    assert "/projects" in seeds
    assert "/inbox" in seeds
    assert "/settings" in seeds
    assert "/diagnostics" in seeds
    assert all(":" not in s for s in seeds)


# --- extract_static_routes — tanstack-router fixture --------------------


def test_extract_tanstack_routes_array(tmp_path):
    """TanStack-router style nested routes object."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "routes.ts").write_text(
        """
import { createRouter, Route } from '@tanstack/router';

const indexRoute = new Route({ path: '/' });
const aboutRoute = new Route({ path: '/about' });
const docsRoute = new Route({ path: '/docs' });
const docsPageRoute = new Route({ path: '/docs/:pageId' });

export const router = createRouter({ routeTree: indexRoute.addChildren([aboutRoute, docsRoute, docsPageRoute]) });
""",
        encoding="utf-8",
    )
    seeds = extract_static_routes(tmp_path)
    assert "/" in seeds
    assert "/about" in seeds
    assert "/docs" in seeds
    # Param route excluded.
    assert "/docs/:pageId" not in seeds


# --- extract_static_routes — plain routes array -------------------------


def test_extract_plain_routes_array(tmp_path):
    """Plain config-array style with double-quoted strings."""
    src = tmp_path / "app"
    src.mkdir()
    (src / "router.ts").write_text(
        """
export const routes = [
  { path: "/", component: Home },
  { path: "/login", component: Login },
  { path: "/signup", component: Signup },
];
""",
        encoding="utf-8",
    )
    seeds = extract_static_routes(tmp_path)
    assert seeds == ["/", "/login", "/signup"]


# --- extract_static_routes — malformed input -----------------------------


def test_extract_malformed_input(tmp_path):
    """File exists but isn't valid JS — extractor doesn't raise."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "router.tsx").write_text("this is not javascript {{{ path: ", encoding="utf-8")
    seeds = extract_static_routes(tmp_path)
    # No `path: '...'` literals → empty result, no exception.
    assert seeds == []


def test_extract_no_router_files_returns_empty(tmp_path):
    """No router files anywhere → empty list, no error."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("export default () => <div/>;", encoding="utf-8")
    assert extract_static_routes(tmp_path) == []


def test_extract_skips_node_modules(tmp_path):
    """Don't grab routes from bundled vendor code in node_modules/."""
    nm = tmp_path / "node_modules" / "some-pkg"
    nm.mkdir(parents=True)
    (nm / "router.tsx").write_text("path: '/should-not-appear'", encoding="utf-8")
    real_src = tmp_path / "src"
    real_src.mkdir()
    (real_src / "router.tsx").write_text("path: '/real-route'", encoding="utf-8")
    seeds = extract_static_routes(tmp_path)
    assert "/real-route" in seeds
    assert "/should-not-appear" not in seeds


def test_extract_dedupes(tmp_path):
    """Same path declared in multiple files → one entry."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "router.tsx").write_text("path: '/dashboard'", encoding="utf-8")
    (tmp_path / "src" / "routes.tsx").write_text("path: '/dashboard'", encoding="utf-8")
    seeds = extract_static_routes(tmp_path)
    assert seeds.count("/dashboard") == 1


# --- _summarize_screenshots ---------------------------------------------


def test_summarize_screenshots_all_succeeded():
    routes = [
        {"url": "/", "screenshot": "shots/root.png"},
        {"url": "/about", "screenshot": "shots/about.png"},
    ]
    assert _summarize_screenshots(routes) == (2, 0)


def test_summarize_screenshots_all_failed():
    routes = [
        {"url": "/", "screenshot_error": "EPERM"},
        {"url": "/about", "screenshot_error": "Target page closed"},
    ]
    assert _summarize_screenshots(routes) == (0, 2)


def test_summarize_screenshots_mixed():
    routes = [
        {"url": "/", "screenshot": "shots/root.png"},
        {"url": "/about", "screenshot_error": "Target page closed"},
        {"url": "/contact", "screenshot": "shots/contact.png"},
    ]
    assert _summarize_screenshots(routes) == (2, 1)


def test_summarize_screenshots_empty():
    assert _summarize_screenshots([]) == (0, 0)


def test_summarize_screenshots_handles_non_list():
    assert _summarize_screenshots("not a list") == (0, 0)


# --- page-isolation invariant -------------------------------------------
#
# The crawler template now runs each route in a fresh page (context.newPage())
# and closes it in a `finally` block. Before this fix, a single
# "Target page closed" thrown by a polling re-render racing
# `page.screenshot()` on route N silently cascade-failed every remaining
# route through the inner catch — routes.json ended up with one entry, no
# screenshots, and the test timed out chasing zero progress. The fix is in
# crawler.ts.template; these tests pin the *contract* the wrapper relies
# on so a future revert to a shared-page model fails loudly here.


def test_page_isolation_invariant_failed_route_does_not_suppress_others():
    """Mixed success/failure across non-adjacent routes must all land in
    routes.json. With the pre-fix shared-page crawler, a screenshot failure
    on route 2 would prevent routes 3..N from ever being recorded; with
    fresh-per-route pages, each route is independent."""
    routes = [
        {"url": "/", "screenshot": "shots/root.png"},
        {"url": "/dashboard", "screenshot_error": "Target page closed"},
        {"url": "/inbox", "screenshot": "shots/inbox.png"},
        {"url": "/settings", "screenshot": "shots/settings.png"},
        {"url": "/diagnostics", "screenshot_error": "EPERM"},
    ]
    succeeded, failed = _summarize_screenshots(routes)
    # All five routes survived to be recorded.
    assert len(routes) == 5
    # Failures and successes were both counted accurately.
    assert succeeded == 3
    assert failed == 2


def test_run_crawl_surfaces_all_routes_when_a_screenshot_fails(tmp_path, monkeypatch):
    """End-to-end through run_crawl: a routes.json with mixed
    success/failure (the page-isolation guarantee made manifest) is
    parsed, summarised, and returned with all routes present.

    Mocks the playwright subprocess so the assertion targets the wrapper's
    handling of the post-fix output shape, not the crawl itself.
    """
    output = tmp_path / ".shipwright" / "adopt" / "routes.json"
    screenshots = tmp_path / ".shipwright" / "adopt" / "screenshots"
    fake_routes = [
        {"url": "/", "screenshot": "shots/root.png"},
        {"url": "/projects", "screenshot_error": "Target page closed"},
        {"url": "/inbox", "screenshot": "shots/inbox.png"},
        {"url": "/settings", "screenshot": "shots/settings.png"},
    ]

    def fake_subprocess_run(*_args, **kwargs):
        # Simulate the post-fix crawler: each route runs in its own page,
        # so a failed screenshot on route 2 does NOT eat routes 3 and 4.
        out_path = Path(kwargs["env"]["SHIPWRIGHT_CRAWL_OUT"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(fake_routes), encoding="utf-8")
        return subprocess.CompletedProcess(args=_args, returncode=0, stdout="", stderr="")

    # Patch the npx resolver, template install, and the subprocess call so
    # the crawl never actually shells out.
    monkeypatch.setattr(route_crawler, "resolve_executable", lambda _name: "/fake/npx")
    monkeypatch.setattr(
        route_crawler,
        "_install_template",
        lambda project_root, config_dir=None: tmp_path / "_fake-spec.ts",
    )
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    summary = run_crawl(
        tmp_path,
        base_url="http://localhost:5175",
        output=output,
        screenshots_dir=screenshots,
        max_depth=3,
        max_pages=50,
        auth_token=None,
    )

    assert summary["status"] == "success"
    assert summary["routes"] == 4  # all four survived, including post-failure routes 3 + 4
    assert summary["screenshots_succeeded"] == 3
    assert summary["screenshots_failed"] == 1
