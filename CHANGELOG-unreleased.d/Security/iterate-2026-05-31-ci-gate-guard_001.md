`security.yml` critical-findings gate now fails closed on a missing or unparseable `findings.json` (previously `2>/dev/null || echo 0` read 0 criticals on a scanner crash and passed green).
