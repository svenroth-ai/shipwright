Goal: Shipwright's own project profile: shipwright-monorepo (claude-plugin plus repo-only rules), configs switched, rules block rendered
Reason: Agents in this repo should read its architecture rules, and repo-only rules must not ship to customers
Reference: campaign profile-architecture-rules, unit U5
Affected ACs: FR-01.01.AC33
AC item: {"confirmed": false, "decided_by": "code", "files": [".shipwright/profiles/shipwright-monorepo.json"], "kind": "add", "new_text": "Given the Shipwright repository uses its own project stack profile, when the profile named in each of its run, project and build configurations is resolved, then every one resolves to that project profile, which equals the bundled plugin profile on everything except its name, description and architecture rules, contains every bundled rule, adds only rules whose checking mechanisms exist and are run by something, and the repository's conventions file carries the current rendered rules block.", "owner_fr": "FR-01.01"}
AC decisions: [{"ac": "FR-01.01.new", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none", "decided_by": "code", "confirmed": false}]
