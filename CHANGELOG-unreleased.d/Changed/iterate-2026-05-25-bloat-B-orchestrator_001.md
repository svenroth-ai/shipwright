- **refactor(run):** split `plugins/shipwright-run/scripts/lib/orchestrator.py`
  (983 LOC) into the `orchestrator_pkg/` package — constants, config I/O,
  legacy migration, config factory, compliance runner, critical gates,
  step planning, build progress, router, and CLI submodules — leaving a
  37-LOC re-export shim at the historical path. All public names and
  ``mocker.patch("orchestrator.X")`` test surfaces stay green; baseline
  entry removed (Campaign B5).
