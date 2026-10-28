# Architecture brief

Problem: a Brief package for a skill-backed app (Claude app is the chat; the app is a skill with a served HTML board + Python backend) goes through Design. Today Design copies the package mockups as the final screens (generic look), and a legacy chat-first path builds a chat+pane layout, which is the wrong product for this app class. The repo ships an Untitled UI kit (CSS + token sets); the package supplies only tokens.

Options:
A. Do nothing: keep adopting mockups unchanged; chat-first stays available for all packages.
B. Prose-only: instruct the design agent to recompose screens from the kit and mark chat-first legacy; no code.
C. Prose plus a small deterministic signal: the apply tool lists which screens are still uncomposed (byte-equal to mockup) so a resume composes exactly those, and refuses chat-first for the skill-backed profile.
D. Compose inside the apply tool (a generator that rewrites mockups to kit HTML).
E. Remove chat-first entirely (schema value, verifier, flows generator, fixture).
