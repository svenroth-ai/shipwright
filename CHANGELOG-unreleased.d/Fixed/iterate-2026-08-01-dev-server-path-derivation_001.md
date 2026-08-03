Replaced the Windows runtime-verifier PID signal probe with a bounded Win32 process-handle wait so liveness checks cannot interrupt their own console group.
