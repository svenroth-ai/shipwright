# Step 3.9: Stop Dev Server (always — finally-block semantics)

**Run unconditionally as a cleanup pass — even if Step 3.7 or Step 3.8
raised or failed.** A blocked test phase is recoverable; a zombie dev server
bound to the dev port is not. Practitioners executing SKILL.md by hand and
CI runners parsing the step list MUST treat this section as a `finally`
clause analogous to a shell `trap`.

```bash
uv run "{plugin_root}/../../shared/scripts/dev_server.py" stop --cwd {project_root}
```
