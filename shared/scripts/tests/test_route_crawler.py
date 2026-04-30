"""Tests for route_crawler.py — static-route extractor + screenshot summary."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from route_crawler import (  # noqa: E402
    _normalize_route,
    _summarize_screenshots,
    extract_static_routes,
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
