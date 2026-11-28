Goal: every recogniser of a moving shipwright_* file (sets, regexes, markers, a pathspec, phase hints) sees it in .shipwright/config/ as well as at the root; labels use name()
Reason: after R3 the root-name recognisers would misclassify a moved file (derived snapshot, sensitive path, FR coverage, project detection)
Reference: campaign root-files-into-config, R1c-3 (BRIEF 12.12 (a))
Catalog gap: FR-01.11
