Goal: gates that read a moving file through git or a missing-file shortcut find it where it lives per commit; the bloat gate fails closed when its baseline is in neither place
Reason: after R3 a moved baseline/config would read as absent at a historical commit, so the bloat gate, AC-baseline growth, events-layout CI and rollout snapshot would silently pass
Reference: campaign root-files-into-config, R1d-1 (BRIEF 4.1, 11.7.4, 14.4)
Catalog gap: FR-01.11
