"""Typed refusal for an otherwise-valid triage status transition."""


class TransitionPreconditionError(ValueError):
    """The resolved card state no longer permits the requested transition."""
