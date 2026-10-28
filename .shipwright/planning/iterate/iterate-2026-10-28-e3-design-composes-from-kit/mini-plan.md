# Mini-plan E3 (attempt 1, Option B: prose only)

Problem: in Brief-package mode Design copies approved mockups into screens/ unchanged; for a skill-backed app the result looks generic.

Decision: attempt 0's architecture review (openai reject, glm revise) named prose-only as the smaller alternative; the campaign took it. No new tool signal, no new refusal.

Change (instructions, docs and one wording fix; no apply-tool change):
1. New reference brief-compose.md: content from the mockup, look from kit.css + package tokens, board layout, no chat layout; a screen that already carries the kit is never recomposed. SKILL.md / upload-mode / step-4 / snippets-layout / untitled-ui-components point to it; chat-first.md and the Layout D snippet marked legacy for skill-backed apps.
2. SKILL.md step B: after the boundary baseline reports written or kept, a red boundary gate is a real STOP (E1 fold-in).
3. Run phase screenshot-gate wording names "approved design screens" not "approved mockups" (phase_validators_late.py) + test.
4. Docs: guide, hooks-and-pipeline, stack-profiles.
Tests: pinned prose, run wording, one kit-composed screen passing the tokens/standalone gates via the existing apply tool + gate script.
Follow-up only if a later run shows prose is insufficient: a deterministic detector.
