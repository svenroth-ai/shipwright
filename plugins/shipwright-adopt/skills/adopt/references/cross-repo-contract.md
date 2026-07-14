# ⚠️ Cross-repo contract — the Command Center renders `snapshot.json`

**This snapshot has an external consumer.** The Command Center WebUI
([shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)) reads
`.shipwright/adopt/snapshot.json` on its **adopt screen** to show the operator
*"what's already here"* (Stack · Routes · Tests · Conventions · CI) **before anything
is written** — the reassurance that nothing of theirs is overwritten.

**A change to this shape requires a corresponding WebUI change.** A key renamed or
dropped — **at any depth**, not just top level — does *not* fail loudly over there; it
renders a half-empty card. The producer is
`scripts/tools/analyze_codebase.py` → `analyze()`.

**Versioning (`SNAPSHOT_SCHEMA_VERSION`, `major.minor`).** **MAJOR** = breaking (a key
removed, renamed or retyped) — the consumer must refuse to render an unrecognised
major rather than half-render it. **MINOR** = additive — the consumer keeps working and
ignores what it does not know, so an addition must not force a WebUI release.
`schema_version` is **additive**: a snapshot written by an older adopt (without the key)
stays readable, and no reader in this repo may come to require it.

**Two subtrees are deliberately NOT pinned** — `stack.{frontend,backend,database,auth,runtime}`
and `folders.loc_by_layer` are **maps keyed by whatever was detected** (`stack.frontend`
is `{"react": …}` in one repo and `{"vue": …}` in the next). Their *keys are the
finding*, so pinning their interiors would pin content, not contract. **The contract for
them is that the consumer must ITERATE them, never index a fixed key.** Everything else
is pinned to full depth — enforced, not asserted: the gate fails on a leaf that no
fixture repo ever populated (`null_only_paths`, `empty_array_paths`), because an
unexercised leaf is an unpinned one, and the published fixture would be telling the
consumer a field is always null when in production it is an object.

**A field becoming nullable is BREAKING** — `test_frameworks.unit` going from
always-an-object to sometimes-null adds no key, so a naive field-graph diff would call
it "no change" while the consumer dereferences null. Nullability is therefore part of
the pinned shape (`object|null`), and gaining a null arm demands a **major**.

**You are not asked to remember this.** `tests/test_snapshot_contract.py` diffs the
emitted snapshot against the contract fixture **as published on `origin/main`**, derives
the bump that diff obliges, and fails until it has been performed. The published fixture
(`tests/contracts/adopt-snapshot-<version>.json`) is **frozen** — a breaking change
cannot be hidden by rewriting the pin, because the baseline is the one thing a pull
request cannot rewrite. To land a shape change: bump the version, add a **new** versioned
fixture, and open the WebUI PR.
