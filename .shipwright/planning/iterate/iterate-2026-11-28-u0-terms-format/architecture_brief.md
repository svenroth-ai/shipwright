# Architecture Brief: intent.md format (U0)
Need: a product owner must see what the product does and accept it without reading ACs. The human owns a short top level (intent, non-goals, capabilities, key scenarios); the AI owns FRs/ACs/links.
Options:
A. Do nothing: keep FR as the top level (FR table + Area column).
B. One human-owned markdown file `.shipwright/planning/intent.md`, one line per element with id and status confirmed|assumption, links to FRs kept AI-side (FR table column, scenario paths table in spec.md); a JSON schema fixes the parsed shape.
C. Store the same elements as JSON/YAML only, rendered to markdown for the human.
D. Extend spec.md with a human-owned section instead of a new file.
Permanent addition for B: one schema, one file per product, five glossary terms, one constitution rule.
