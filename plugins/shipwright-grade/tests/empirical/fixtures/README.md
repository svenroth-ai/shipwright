# Empirical replay fixtures

Cached payloads for the empirical calibration suite (`-m empirical`).

Each file is `record/replay` output keyed by `<repo>@<sha>` — the projected
signals for a pinned commit of a real OSS repo. The suite **replays** from these
so it stays deterministic and does not rot when GitHub expires run logs
(~90 days). Network is only needed to *refresh* a payload.

**G1 seeds the harness; this directory is intentionally empty of payloads.** The
real commit SHAs, the recorded payloads, the full curated repo spread, the
sample-report gallery and the launch gate are added in **G5**.
