"""`shared/scripts/lib/html_tag_scanner.py` — the quote-aware tag/attribute
scanner extracted from `design_gate_extras.py` (PR #726 round 8b).
"""

from lib.html_tag_scanner import parse_tags


def test_a_greater_than_inside_a_quoted_attribute_does_not_truncate_the_tag():
    html = '<a onclick="items.map(i => i)" href="99-secret.html" class="nav-item">Secret</a>'
    tags = parse_tags(html)
    assert len(tags) == 1
    assert tags[0]["href"] == "99-secret.html"
    assert tags[0]["class"] == "nav-item"


def test_a_duplicated_attribute_resolves_first_wins():
    html = '<script src="https://evil.example/x.js" src="local.js"></script>'
    tags = parse_tags(html)
    assert tags[0]["src"] == "https://evil.example/x.js"


def test_an_unquoted_attribute_value_is_still_captured():
    html = "<script src=https://cdn.example.com/lib.js></script>"
    tags = parse_tags(html)
    assert tags[0]["src"] == "https://cdn.example.com/lib.js"


def test_a_self_closing_tag_is_also_captured():
    html = '<img src="logo.png" class="nav-item" />'
    tags = parse_tags(html)
    assert tags[0]["src"] == "logo.png"


def test_comments_and_script_bodies_are_not_parsed_as_tags():
    html = "<!-- <a href='fake.html'>not a tag</a> --><a href='real.html'>real</a>"
    tags = parse_tags(html)
    assert [t.get("href") for t in tags] == ["real.html"]


def test_attribute_names_are_lowercased():
    html = '<A HREF="dashboard.html" CLASS="nav-item">Dashboard</A>'
    tags = parse_tags(html)
    assert tags[0]["href"] == "dashboard.html"
    assert tags[0]["class"] == "nav-item"
