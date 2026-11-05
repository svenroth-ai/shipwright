Goal: Release manifest sync can declare package-lock.json (package_lock_json) and writes both version fields.
Reason: Lockfiles stayed on the old version after a release and dirtied the tree on the next npm install.
Reference: operator request 2026-11-05
