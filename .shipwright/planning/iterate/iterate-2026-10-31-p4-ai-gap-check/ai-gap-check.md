### Independent gap check (openai/gpt-6.1-sol)

Advisory only; it never blocks. It checks the declaration against the diff for a wrong "none" and for catalog gaps.

- Requirements changed: none
- Requirements checked: FR-01.11.AC49 (Adds an independent advisory review, a pull-request note, and visible reasons when the review cannot run.); FR-01.11.AC47 (Reads the author's requirement declaration without changing how that declaration is required.); FR-01.11.AC48 (Reports gaps without changing the existing rules for closing declared gaps.); FR-01.11.AC44 (Registers the new warning in the shared set of finalization checks.)
- Check verdict on the declaration: **agree**
- Catalog gap: **no**
- Reason: The change adds the advisory independent check under the requirement the author named. The new criterion describes that behavior and closes the declared gap, so no uncovered product behavior remains evident.
