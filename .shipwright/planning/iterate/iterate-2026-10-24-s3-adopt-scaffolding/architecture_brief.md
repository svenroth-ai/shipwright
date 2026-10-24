# Architecture brief: how should adopt learn about custom stack profiles?

Context: stack profiles can now live in the project, the user home or the bundled tree; a resolver module (project > user > bundled, first file wins, no fall-through) and loader glue already exist. Adopt still scans only the bundled folder for matching, silently degrades to `generic` when that folder is missing, picks CI/CodeQL templates by profile NAME, and may crash half-way through writing when an override or snapshot-selected profile is unknown.

Options:
A. Adopt resolves everything through the existing resolver: the matcher scans an ordered list of directories, the effective profile is resolved once before any write, and name-keyed templates apply only when the resolved source is bundled.
B. Leave adopt bundled-only; custom profiles are only usable after adoption through the other phases.
C. Make adopt copy a matched custom profile into the bundled tree or invent adopt-specific lookup code.

Smallest thing that would do: A, with the glue in one small adopt module and no new lookup logic.
