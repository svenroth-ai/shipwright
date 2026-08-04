#!/usr/bin/env python3
"""Handshake launcher used to place a Windows F0 process tree in a Job Object."""

from __future__ import annotations

import subprocess  # nosec B404 - argv is supplied by the validated suite runner
import sys


def main() -> int:
    try:
        separator = sys.argv.index("--")
    except ValueError:
        return 126
    argv = sys.argv[separator + 1:]
    if not argv:
        return 126
    # The parent assigns this blocked process to its kill-on-close Job Object before
    # sending the byte. Every process created below therefore inherits that job.
    if not sys.stdin.buffer.read(1):
        return 126
    try:
        child = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL)  # nosec B603
        return child.wait()
    except OSError:
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
