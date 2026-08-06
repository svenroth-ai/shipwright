# Events context cost

> Temporary P1.15 observation output. It is generated for the operator and is not an agent startup input.

## Latest iterate

- **Run:** `iterate-2026-08-06-triage-store-write-path`
- **Mode:** `compact`
- **Reduction:** 96.4%
- **Selected:** 15 of 799 events; 5316 of 147162 estimated tokens
- **Queries / truncations / fallbacks:** 1 / 1 / 1
- **Fallbacks:** catalog_stale

## Rolling values (last 3 observations)

| Measure | Latest | Rolling average |
|---|---:|---:|
| Full events | 799 | 772.7 |
| Full bytes | 588646 | 537918.3 |
| Full estimated tokens | 147162 | 134480.0 |
| Selected events | 15 | 15.0 |
| Selected bytes | 21262 | 23979.0 |
| Selected estimated tokens | 5316 | 5995.0 |
| Reduction % | 96.4 | 95.5 |

Counts are measured from the raw log and the emitted structured event payload. Estimated tokens use the deterministic `ceil(bytes / 4)` approximation.
