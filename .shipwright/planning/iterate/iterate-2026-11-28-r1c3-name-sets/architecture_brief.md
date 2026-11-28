# Architecture brief: R1c-3 (recognisers see both places)

**Problem.** Shipwright keeps about 30 `shipwright_*` files at the project root. The campaign moves them into `.shipwright/config/` (R3). R1c-1 and R1c-2 made every reader and writer find a file in either place through one lookup, `path(key, root)`. Code that RECOGNISES a file by its path still knows only the root name. That includes:
- derived-snapshot and churn sets (what an iterate must not commit, what merge conflicts resolve automatically);
- review-size and attribution sets;
- the sensitive-path regex and skip-review set of the required PR-review gate;
- project markers ("is this a Shipwright project?");
- one git pathspec;
- phase hints and messages.

After the move these would silently misclassify the moved file.

**Proposed change.** Recognisers ask the registry for every known location of a key, `known_rels(key)` (new, then legacy), instead of the root name. Readers that report a place report the resolved one. Pure labels use `name(key)`, the bare file name. The event log does not move and stays as it is. An AST test forbids spelling a moving file by its root name (`rel`/`legacy_rel`) in production code, apart from two named exceptions.

**Alternatives.**
1. Do nothing until R3 and switch `rel()` to the new place then. Rejected: a set would then hold ONLY the new place, while existing repos keep the root copy until they migrate. Both places must be recognised during the transition.
2. Match on basename everywhere. Rejected: it widens the security sets. A planted file named like a ledger elsewhere must not borrow its classification.

**Constraints.** No behaviour change in an unmigrated repo: the sets only gain paths that do not exist. Files stay at or under 300 lines.
