"""Backwards-compat shim — the real code lives in ``collectors/``.

Iterate Campaign B (B2): the 1559-LOC ``data_collector.py`` monolith
was split into the ``collectors/`` package (one module per logical
domain: dashboard, rtm, test_evidence, change_history, sbom). This
shim re-exports the pre-split public surface so existing imports
(including ``shared.contracts.compliance`` and every test under
``tests/test_data_collector*.py``) keep working unchanged.

New code SHOULD import from ``scripts.lib.collectors`` directly. The
shim is kept for backwards compatibility, not as the recommended
import path.
"""

from __future__ import annotations

# Public surface (dataclasses + collectors + constants + collect_all)
from .collectors import *  # noqa: F401,F403
from .collectors._common import CONFIG_FILES  # noqa: F401
from .collectors._npm_license import (  # noqa: F401
    _read_npm_lockfile_licenses,
    detect_npm_license as _detect_npm_license,
)
from .collectors._python_license import (  # noqa: F401
    detect_python_license as _detect_python_license,
    parse_pyproject_deps as _parse_pyproject_deps,
)
from .collectors.change_history import (  # noqa: F401
    EVENT_FILE,
    _apply_amendments,
    _read_event_log,
    _resolve_events_path,
    latest_event_timestamp as _latest_event_timestamp,
)
from .collectors.dashboard import (  # noqa: F401
    _sections_from_data,
    map_requirements_to_sections as _map_requirements_to_sections,
)
from .collectors.rtm import (  # noqa: F401
    map_requirements_to_events as _map_requirements_to_events,
)
