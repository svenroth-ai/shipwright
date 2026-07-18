"""Golden corpus freezing today's requirements discovery + parsing behaviour.

Campaign "Requirements Catalog" sub-iterate **S1**
(``Spec/design/2026-07-18-requirements-catalog-campaign-SPEC.md`` section 4).

Steps S2-S4 of that campaign rewrite the discovery and parsing machinery and
claim to be behaviour-preserving. This package exists so that claim can be
CHECKED rather than asserted.

**This corpus freezes today's behaviour INCLUDING its bugs.** Assertions that
look wrong are wrong on purpose; every one carries a ``FROZEN-BUG:`` comment
naming the campaign step that flips it. Do not "fix" a surprising expected
value here -- fixing it destroys the baseline the refactor is measured against.

Layout:

``corpus_data.py``   the fixture markdown, as data
``corpus.py``        materializes a fixture into a tmp_path project root
``registry.py``      the target inventory (SSoT) -- 15 discovery + 5 parser
``_collect_realm.py``runs INSIDE a subprocess: loads one import realm, invokes
                     its targets, emits JSON
``collect.py``       orchestrates the six realm subprocesses, merges results
``golden.json``      the committed baseline
``regen_golden.py``  deliberate regeneration (NOT a pytest flag -- see below)

**Why regeneration is a separate script and not ``--update-golden``:** a pytest
flag lets someone rerun-to-green the moment S2 breaks this harness, which would
make the behaviour-preserving claim self-certifying and destroy the one
guarantee this corpus exists to provide. Friction is the feature.
"""
