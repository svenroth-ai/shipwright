"""Real lexical scope-chain resolution for
`shared/scripts/lib/triage_plain_append_scan.py` -- split out once that file
crossed 300 lines, the same reason `test_triage_precondition_registry.py`
was split from `test_triage_precondition_callers.py`. This half owns the
scope/shadowing MECHANISM; the parent module owns what counts as a match.

Five external-review rounds (5-9, openai every round, GLM twice,
iterate-2026-09-16-e5) found successive defects on the way to this shape:

- Round 5: a fully UNSCOPED walk let a function-local `import triage` (a
  lazy-import helper -- `suite_race_triage.py::_load_triage` is a real,
  live example) taint an UNRELATED function's own same-named parameter
  (`_open_ids(triage, ...)`, same file).
- Round 6: the fix that then restricted collection to MODULE scope only
  made an ordinary function-local `from triage import append_triage_item`
  invisible even to a call in the SAME function.
- Round 7: nesting without SHADOWING still flagged `def emit(triage):
  triage.append_triage_item(...)` against an unrelated module-level
  `import triage`, because a bare parameter was invisible to the walk
  entirely.
- Round 8 (openai, medium): shadowing without ORDER-INDEPENDENT precedence
  still resolved `from triage import append_triage_item;
  append_triage_item = other_writer; append_triage_item(...)` as a hit,
  because the import binding and the later reassignment landed in the SAME
  scope and the import was checked first regardless. `target_names` and
  `other_names` (below) are now tracked SEPARATELY per scope so a
  same-scope conflict resolves to "ambiguous, do not flag" rather than
  "import wins by accident of check order".
- Round 9 (GLM, medium): the `ImportFrom` match compared `node.module`
  without checking `node.level`, so a RELATIVE import literally named
  `.triage` (`from .triage import append_triage_item`) matched as if it
  were the real, absolute module -- fixed by requiring `level == 0`.

`build_scope_bindings` + `resolve` close all four: a name is visible to a
call if bound to the searched-for thing in that call's own scope or any
scope enclosing it -- but the FIRST scope that binds the name AT ALL wins.
If that scope binds it ONLY to the thing being searched for, that's a hit.
If it ALSO (or instead) binds the name to anything else -- a parameter, an
unrelated import, a reassignment, any other local binding -- that scope's
binding is ambiguous or a shadow, a dead end, not a fall-through to the
parent. This is exactly how Python's own compiler decides a name is "local"
to a function: if anything inside a function's body binds a name, anywhere
in the body, that name is local throughout it, regardless of statement
order.

Comprehensions (`ListComp`/`SetComp`/`DictComp`/`GeneratorExp`) are real
lexical scopes in Python 3 (round 8, GLM, medium: `[triage for triage in
items]` must not leak `triage` into the ENCLOSING function, or a later,
unrelated `triage.append_triage_item(...)` in that function would be
missed) -- included in `_SCOPE_BOUNDARIES` for that reason.

**Six accepted gaps, all narrow and all rare enough in real code that
modelling them is the over-engineering the campaign's own D7 abort
condition warns against:**

1. `global`/`nonlocal` declarations are not honoured (round 8, GLM, low) --
   a name declared `global` inside a function and bound there is treated
   as local to that function, not redirected to module scope.
2. A `def`'s decorators, parameter defaults, and annotations are visited
   in the function's OWN scope (round 8, GLM, low); real Python evaluates
   them in the ENCLOSING scope instead.
3. Order-independence is a two-way trade-off, not just the round-8 fix's
   safe direction (round 9, openai, "bug", high): `resolve` cannot tell a
   reassignment BEFORE a real call (which SHOULD still flag: `from triage
   import append_triage_item; append_triage_item(...); append_triage_item
   = replacement`) from one AFTER it (which should not, round 8's actual
   finding) -- both look identical without tracking statement order/control
   flow, a materially bigger undertaking than the ambiguity it would
   remove. Chosen direction: never flag an ambiguous same-scope conflict,
   favouring no false positive over completeness for this rare shape.
4. A walrus target (`ast.NamedExpr`) inside a comprehension is recorded in
   the COMPREHENSION's own scope (round 9, GLM, low); real Python binds it
   in the comprehension's ENCLOSING scope instead, which could misresolve
   a call on either side of the comprehension in a sufficiently contrived
   case.
5. A star import from an UNRELATED module (`from other import *`) records
   no binding at all (round 10, GLM, low), so it cannot conflict with a
   same-scope `from triage import append_triage_item` even if `other`
   happens to export a same-named symbol too -- contrived, since it needs
   two star imports of the exact target name from two different modules at
   one scope.
6. `import triage.sub` (a dotted import whose FIRST component happens to be
   `triage`) is recorded, via its first component, in `other_names` exactly
   like an unrelated `import triage` would be (round 10, GLM, low) -- so it
   can shadow a genuine `import triage` in an enclosing scope even though
   no such dotted import of the REAL `triage.py` (a flat module, not a
   package) has ever existed in this repo, checked the same way limit #1
   was.

**One accepted imprecision, in the SAFE direction:** a `ClassDef` body's own
import is treated as visible to that class's methods, though real Python
does not extend class-body scope into methods (a bare
`triage.append_triage_item(...)` there would actually raise `NameError` at
runtime, not silently duplicate). Over-flagging code that could not even
run is a strictly safer failure mode than the scan-gap this module exists
to close, so it is accepted rather than special-cased.
"""

from __future__ import annotations

import ast

#: Node types that open a new lexical scope -- a binding inside one of
#: these is visible only there and in scopes nested inside it, never in a
#: sibling scope (real Python name resolution). Comprehensions are included
#: because their `for`/walrus targets are genuinely their own scope, not
#: the enclosing function's.
_SCOPE_BOUNDARIES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
_NAMED_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def build_scope_bindings(tree: ast.AST, *, target_name: str, module_name: str):
    """One walk of `tree`, returning everything `resolve` needs to check a
    call against its own scope chain, with real Python shadowing:

    - `parent`: each scope node's nearest ENCLOSING scope (`None` for the
      module `tree` itself).
    - `plain_names` / `module_aliases`: names a scope directly binds to
      `target_name` (an import FROM `module_name` by its exact literal
      name, or a star import) and to `module_name` ITSELF (a plain
      `import`/`as` alias), respectively -- what a bare-name call and an
      attribute call's object must each resolve to, for a HIT.
    - `other_names`: EVERY name a scope directly binds to anything ELSE --
      parameters, assignment/`for`/`with`-as/walrus targets, `except ...
      as` names, a reassignment of a name already in `plain_names` /
      `module_aliases` at the SAME scope, any other import (even one
      unrelated to `module_name`), and a nested `def`/`class`'s own name
      (bound in the scope that DEFINES it). Tracked SEPARATELY from
      `plain_names`/`module_aliases` so `resolve` can tell "this scope
      binds the name to the thing we want" from "this scope ALSO binds the
      name to something else" -- the latter makes a same-scope match
      ambiguous, not a hit (round 8 finding).
    - `call_scope`: every `ast.Call` node mapped to the scope it lexically
      sits in.
    """
    parent: dict[ast.AST, ast.AST | None] = {tree: None}
    plain_names: dict[ast.AST, set[str]] = {}
    module_aliases: dict[ast.AST, set[str]] = {}
    other_names: dict[ast.AST, set[str]] = {}
    call_scope: dict[ast.Call, ast.AST] = {}

    def bind_other(scope: ast.AST, name: str) -> None:
        other_names.setdefault(scope, set()).add(name)

    def visit(node: ast.AST, scope: ast.AST) -> None:
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == module_name
        ):
            # Round 9 external review (GLM, medium): `node.level == 0` is
            # required -- without it, a RELATIVE import literally named
            # `.triage` (`from .triage import append_triage_item`, level=1)
            # matched too, even though it is not the real, absolute
            # `triage` module this scanner resolves (the one convention
            # every real producer uses, `sys.path.insert(...)` + a bare
            # `import triage`). An absolute import always has `level == 0`.
            for alias in node.names:
                if alias.name == "*":
                    plain_names.setdefault(scope, set()).add(target_name)
                elif alias.name == target_name:
                    plain_names.setdefault(scope, set()).add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            # Not FROM the target module -- still a real binding, so it can
            # shadow (or, at the same scope, conflict with) a same-named
            # import FROM it.
            for alias in node.names:
                if alias.name != "*":
                    bind_other(scope, alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module_name:
                    module_aliases.setdefault(scope, set()).add(alias.asname or alias.name)
                else:
                    bind_other(scope, alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            call_scope[node] = scope
        elif isinstance(node, ast.arg):
            bind_other(scope, node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bind_other(scope, node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bind_other(scope, node.name)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPE_BOUNDARIES):
                if isinstance(child, _NAMED_SCOPE_BOUNDARIES):
                    bind_other(scope, child.name)
                parent[child] = scope
                visit(child, child)
            else:
                visit(child, scope)

    visit(tree, tree)
    return parent, plain_names, module_aliases, other_names, call_scope


def resolve(
    scope: ast.AST,
    name: str,
    target_names: dict[ast.AST, set[str]],
    other_names: dict[ast.AST, set[str]],
    parent: dict[ast.AST, ast.AST | None],
) -> bool:
    """Is `name`, used in `scope`, bound to the thing `target_names` records
    -- walking outward and stopping at the FIRST scope that binds `name` at
    all. A scope binding the name to `target_names` AND NOTHING ELSE is a
    hit; a scope binding it to anything in `other_names` (whether or not
    `target_names` ALSO has it -- an ambiguous same-scope conflict, round 8
    finding) is a shadow, a dead end, not a fall-through to the parent.
    """
    node: ast.AST | None = scope
    while node is not None:
        if name in other_names.get(node, ()):
            return False
        if name in target_names.get(node, ()):
            return True
        node = parent.get(node)
    return False
