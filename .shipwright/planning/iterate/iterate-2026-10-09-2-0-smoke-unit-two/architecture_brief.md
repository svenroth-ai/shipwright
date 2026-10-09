# Architecture Brief: smoke unit 2 file-presence check

## The problem
A throwaway smoke campaign needs a small, real code change per unit to exercise the campaign
runner end-to-end (PR #860 verification). The change itself will never be merged.

## What would newly, permanently exist
Nothing permanent: a standalone script that checks one marker file exists and is non-empty, the
marker file, and a test. No gate, hook, CI job, or caller invokes the script; the branch is
discarded after the smoke run.
