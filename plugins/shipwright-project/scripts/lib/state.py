"""State detection for /shipwright-project resume support.

Derives state from file existence, not JSON fields.

Checkpoints:
- shipwright_project_interview.md exists -> interview complete (step 2)
- project-manifest.md exists -> proposal complete (step 4)
- NN-name/ directories exist -> directories created (step 6)
- NN-name/spec.md for all splits -> specs complete (step 7)
- CLAUDE.md exists in project root -> scaffolding complete (step 8)
"""

import re
from pathlib import Path
from typing import TypedDict

from .config import SessionFilename


class DetectStateResult(TypedDict):
    """Return type for detect_state()."""

    interview_complete: bool
    manifest_created: bool
    directories_created: bool
    splits: list[str]
    splits_with_specs: list[str]
    resume_step: int


SPLIT_DIR_PATTERN = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_valid_split_dir(name: str) -> bool:
    """Check if directory name matches split directory pattern."""
    return bool(SPLIT_DIR_PATTERN.match(name))


def get_split_index(name: str) -> int:
    """Extract numeric index from split directory name."""
    return int(name[:2])


def detect_state(planning_dir: Path | str) -> DetectStateResult:
    """Detect current workflow state from file existence."""
    planning_dir = Path(planning_dir)

    interview_complete = (planning_dir / SessionFilename.INTERVIEW).exists()
    manifest_created = (planning_dir / SessionFilename.MANIFEST).exists()

    splits = sorted(
        [
            d.name
            for d in planning_dir.iterdir()
            if d.is_dir() and is_valid_split_dir(d.name)
        ],
        key=get_split_index,
    )

    splits_with_specs = [
        s for s in splits if (planning_dir / s / "spec.md").exists()
    ]

    directories_created = len(splits) > 0

    # Determine resume step
    # Steps 3 and 5 are never resume points (inline after 2 and 4)
    # Step 7 is scaffolding (Shipwright enhancement)
    # Step 8 is complete
    if directories_created and len(splits_with_specs) == len(splits) and splits:
        resume_step = 7  # Scaffolding (or complete if CLAUDE.md exists)
    elif directories_created:
        resume_step = 6  # Spec generation
    elif manifest_created:
        resume_step = 4  # User confirmation
    elif interview_complete:
        resume_step = 2  # Split analysis
    else:
        resume_step = 1  # Interview

    return {
        "interview_complete": interview_complete,
        "manifest_created": manifest_created,
        "directories_created": directories_created,
        "splits": splits,
        "splits_with_specs": splits_with_specs,
        "resume_step": resume_step,
    }
