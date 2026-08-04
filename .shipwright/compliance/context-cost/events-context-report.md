# Events context cost

> Temporary P1.15 observation output. It is generated for the operator and is not an agent startup input.

## Latest iterate

- **Run:** `iterate-2026-08-04-p1-15-events-context`
- **Mode:** `compact`
- **Reduction:** 95.3%
- **Selected:** 15 of 758 events; 5982 of 127672 estimated tokens
- **Queries / truncations / fallbacks:** 1 / 1 / 1
- **Fallbacks:** catalog_missing

## Rolling values (last 1 observation)

| Measure | Latest | Rolling average |
|---|---:|---:|
| Full events | 758 | 758.0 |
| Full bytes | 510687 | 510687.0 |
| Full estimated tokens | 127672 | 127672.0 |
| Selected events | 15 | 15.0 |
| Selected bytes | 23927 | 23927.0 |
| Selected estimated tokens | 5982 | 5982.0 |
| Reduction % | 95.3 | 95.3 |

Counts are measured from the raw log and the emitted structured event payload. Estimated tokens use the deterministic `ceil(bytes / 4)` approximation.
