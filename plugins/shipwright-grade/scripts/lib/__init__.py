"""shipwright-grade core library — cold-repo → GradeInputs projector.

Modules are imported bare (the plugin's ``scripts/lib`` is placed on
``sys.path`` by ``tests/conftest.py`` and by the ``grade.py`` CLI wrapper), so
this package never occupies the dotted ``scripts.lib`` namespace. That keeps the
cross-plugin ``engine_bridge`` import of the compliance plugin's
``scripts.lib.control_grade`` collision-free (ADR-045).
"""
