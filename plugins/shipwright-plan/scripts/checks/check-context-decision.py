#!/usr/bin/env python3
"""Context window check prompt for /shipwright-plan.

Outputs a prompt that reminds the agent to assess context window usage
before writing large artifacts (plan, sections).
"""

import json


def main() -> int:
    print(json.dumps({
        "prompt": (
            "Before proceeding, assess your context window usage. "
            "If you've done extensive research and interviewing, consider: "
            "(1) Summarize key findings before writing the plan, "
            "(2) If context is very large, suggest /clear and resume. "
            "Session state ensures seamless resume from any step."
        ),
        "action": "self_assess",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
