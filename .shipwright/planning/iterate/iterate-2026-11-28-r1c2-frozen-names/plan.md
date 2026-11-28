Goal: every reader and writer of a moving shipwright_* file resolves it through path(), so the file is found in .shipwright/config/ as well as at the root
Reason: about 60 modules joined the root to a name frozen at import and would miss the files R3 moves
Reference: campaign root-files-into-config, R1c-2 (BRIEF 12 items 10-12)
Catalog gap: FR-01.11
