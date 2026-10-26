# Architecture brief: design for chat-first Brief packages

Problem: a Brief package with `ux_shape: chat-first` describes an app that is a chat plus a pane. Today the design phase only knows page-style layouts and navigation chrome, so for such a package it has no layout to draw on, no way to tie the commands a user types to the pane screen that shows their result, and the flows gate needs flow mockups nobody generates.

What would newly, permanently exist: a `chat-map.json` file format (chat-only capabilities, golden paths) read by the design tool, one generated flow mockup per golden path, a layout snippet, one extra design verifier check and one extra rule in the chrome gate (a chat chip must not carry navigation classes). A complete example package ships under integration-tests/fixtures.

Options on the table:
- A: extend the existing `apply-brief-package.py` tool with a chat-map check and flow generation, shared planning module, verifier beside the existing one.
- B: prose only: the agent reads chat-map.json and authors flows by hand.
- C: a separate chat-first design tool.
- D: do nothing: chat-first packages use the classic layouts, flows written by the operator.

Constraints: the package hash is verified before use; no FR id is typed by the agent; shared code loads by file path (ADR-045); existing gates stay unchanged for classic packages.
