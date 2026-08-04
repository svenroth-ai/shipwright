# Events context cost

> Temporary P1.15 observation output. It is generated for the operator and is not an agent startup input.

## Latest iterate

- **Run:** `iterate-2026-08-04-runtime-process-identity`
- **Mode:** `compact`
- **Reduction:** 94.8%
- **Selected:** 15 of 761 events; 6687 of 128606 estimated tokens
- **Queries / truncations / fallbacks:** 1 / 1 / 1
- **Fallbacks:** catalog_stale

## Rolling values (last 2 observations)

| Measure | Latest | Rolling average |
|---|---:|---:|
| Full events | 761 | 759.5 |
| Full bytes | 514422 | 512554.5 |
| Full estimated tokens | 128606 | 128139.0 |
| Selected events | 15 | 15.0 |
| Selected bytes | 26748 | 25337.5 |
| Selected estimated tokens | 6687 | 6334.5 |
| Reduction % | 94.8 | 95.0 |

Counts are measured from the raw log and the emitted structured event payload. Estimated tokens use the deterministic `ceil(bytes / 4)` approximation.
