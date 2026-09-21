# Canonical plugin-root resolver + deterministic Codex bundle builder

## Context

Shipwright's hooks and skills read `CLAUDE_PLUGIN_ROOT` to find their own
plugin's files. That variable is Claude-specific; Codex sets `PLUGIN_ROOT`
instead and has no business reading Claude's plugin cache. Before this
iterate, nothing let a script resolve its own root the same way regardless of
which assistant installed it, and Shipwright had no way to be installed for
Codex at all except as a prose pointer into `~/.claude/plugins/cache`.

This is R1 of the `codex-plugin-execution-reliability` campaign, pulling
forward M1+M2 from `Spec/codex-runtime-integration-spec.md` §7. It is
infrastructure only — no enforcement or runtime behavior change (that is
R2/M3).

## Decision

Add one canonical resolver, `shared/scripts/lib/plugin_root.py`, with env
precedence `SHIPWRIGHT_PLUGIN_ROOT` > `CLAUDE_PLUGIN_ROOT` > `PLUGIN_ROOT`
(Codex-native, checked last), raising when none is set. Add a deterministic
builder (`shared/scripts/tools/build_codex_plugin.py`) that flattens all 14
plugin manifests + `shared/` into one `.codex-plugin/plugin.json` bundle
(gitignored `dist/codex-plugin/`), plus a paired drift/provenance verifier
(`verify_codex_plugin_bundle.py`). Migrate the three real
`CLAUDE_PLUGIN_ROOT`-reading call sites
(`capture_session_id.py`, `audit_phase_quality_on_stop.py`,
`audit_compliance_on_stop.py`) to the shared resolver.

## Consequences

Any script — hook or skill-launched — resolves its own plugin root
identically whether invoked from the monorepo, a Claude plugin-cache
install, or a Codex plugin-cache install. Shipwright can be installed into a
real Codex session from a local file-based marketplace, with every skill
discoverable by name (proven live during this iterate — see AC1 evidence).
A stale or drifted bundle is caught mechanically rather than by hand-diffing
a copied tree. No change to `.claude-plugin/marketplace.json` or any of the
14 `plugins/*/.claude-plugin/plugin.json` files (AC6).

## Rationale

`SHIPWRIGHT_PLUGIN_ROOT` is framework-owned and checked first so a future
non-Claude, non-Codex host only needs to set one variable. `CLAUDE_PLUGIN_ROOT`
outranks the Codex-native `PLUGIN_ROOT` because Claude is the shipping today;
Codex is additive. The resolver is a value-level contract only — it returns
whichever env var was set, verbatim, and does not parse or guess cache
topology; it does NOT prove that logic which *does* parse the plugin-root
path (e.g. `phase_from_plugin_root()`'s `shipwright-<phase>` name matching,
used by the two audit hooks) recognizes a phase under the real Codex bundle,
which installs as one umbrella plugin
(`.../cache/shipwright/shipwright/<version>/`, confirmed live) with no
per-plugin name component to match against — that gap is unsolved and out of
this iterate's scope (see Out of Scope below).

`plugins/shipwright-build/scripts/hooks/cleanup-review-scratch-on-code-reviewer-failure.py`
is NOT migrated to import the shared resolver — it inlines the same
three-variable precedence instead, per its own ADR-044 self-containment
constraint (no cross-plugin `shared/` import from this hook, which would risk
a pytest `sys.path` collision across plugin test roots). Its
`resolve_shared_root()` also had to gain a second directory-shape fallback:
the Codex umbrella bundle puts `shared/` as a direct sibling of a plugin's
scripts (`<bundle_root>/shared`), while the Claude plugin cache puts it two
levels up (`<plugin>/../../shared`) — trying only the cache shape silently
no-op'd this hook forever under a live Codex bundle install. This was found
only by external LLM review (both `glm` and `openai` independently), after
slipping through 4 rounds of internal doubt-review and 2 rounds of internal
code-review, because neither internal round explicitly modeled the runtime
directory-shape difference between the two install targets.

`build_codex_plugin.py` also gained a same-named-skill-across-plugins
collision guard (`BundleCollisionError`) during Internal Plan Review — two
plugins declaring a skill with the same directory name would otherwise
silently flatten to one, discarding the other.

Two "high"-severity external plan-review findings were verified false and
declined with rebuttal evidence recorded in the iterate spec rather than
acted on: (1) a claim that `resolve_plugin_root()` returns a bare `Path` in
violation of AC2's string-preservation contract — false, a verbatim-string
`resolve_plugin_root_str() -> str` already exists as the canonical resolver
for that use; (2) a claim that the mini-plan's call-site migration list
undercounts scope to one file — checked against the mini-plan text directly
and found it already lists all three real call sites correctly (a separate,
real staleness in a different line of the same mini-plan — an outdated
scope-count comment — was found independently by external code review and
was fixed).

## Rejected alternatives

Committing the built bundle into the repo instead of gitignoring
`dist/codex-plugin/` was considered and rejected: it would make the bundle
installable from a bare checkout without a build step, but a generated
multi-hundred-file copy of 14 plugins + `shared/` is exactly the kind of
drift-prone generated artifact this repo's own "where documents live"
convention keeps out of hand-written trees, it would roughly multiply this
iterate's diff size for no verification benefit the drift checker doesn't
already provide, and publication-readiness is explicitly out of this
campaign's scope (revisit only when an actual publish/distribution iterate
needs it).

## Out of scope

Phase-aware hook behavior under the real Codex-installed bundle (the
umbrella-plugin name-matching gap noted above), and the M3 enforcement/
runtime-behavior layer this bundle-and-resolver infrastructure is built to
support — both deferred to a later sub-iterate of
`codex-plugin-execution-reliability`.

## Process note

Spec-reviewer, Internal Plan Review (opus-plan-reviewer), and External Plan
Review were run **late** relative to their normal pre-build timing during
this run, after the gap was discovered mid-session; each was still run to
completion and its findings addressed before finalization, and the timing
violation is recorded honestly in the iterate spec rather than silently
back-filled.
