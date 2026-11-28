# Architecture Brief: root pyproject.toml and uv.lock as release manifests

## The problem
A release of this repo writes its version into every declared manifest, but the root `pyproject.toml`
and the project's own entry in `uv.lock` are not declarable, so the last release left them one version
behind (they had been bumped by hand before).

## What would newly, permanently exist
Nothing new as a mechanism. The existing release manifest sync (one config list, one write step, one
verify-against-the-commit step) learns two more file formats, and this repo lists its two root files.
