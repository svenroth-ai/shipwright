# Mini-plan: outbox-only amend delivery signal

1. Extend the triage delivery leaf with an accumulating valid-amend calculation:
   a tracked append is required, invalid/orphan events are ignored, and a canonical
   tracked copy marks an outbox amend delivered.
2. Carry the fact through `store_facts`, the CLI, and the contract as an always
   present row boolean plus a capped sibling envelope block.
3. Retain contract v2 under the established additive-field compatibility rule;
   record the exact WebUI handoff without modifying that repository.
4. Prove tracked-only, amend-only, status-only, combined, invalid/orphan, and
   post-sweep cases through focused units and the real CLI boundary.

## Alternative considered

Widen `undeliveredDecisions` to include amend ids. Rejected because one card with
both buffered facts would collapse two independent delivery signals and change the
meaning a current consumer already uses.
