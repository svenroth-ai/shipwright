Goal: path() finds each moving shipwright_* file in .shipwright/config/ first, then at the root, and refuses loudly when the layout is broken
Reason: R3 moves the root files into .shipwright/config/; every reader must already find them there and nothing may silently pick the wrong copy
Reference: campaign root-files-into-config, R1c-1 (BRIEF 4.7, 12 item 11)
Catalog gap: FR-01.11
