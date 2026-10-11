"""Typed, loud exit states for the oa CLI.

Every oa command exits through one of these so a caller (script, CI, judge) can tell a
genuinely blocked/unimplemented path from a real pass or fail without parsing prose.
"""

from __future__ import annotations

import enum


class ExitState(enum.IntEnum):
    """Process exit codes. Never reuse a code for two different meanings."""

    OK = 0
    NOT_IMPLEMENTED = 2
    BLOCKED_NO_CREDENTIAL = 3
    BUDGET_EXCEEDED = 4
    VALIDATION_FAILED = 5
    INFRA_ERROR = 6
    CANCELLED = 7


class NotImplementedExit(Exception):
    """Raised by a command that is registered but not yet built.

    This must never be caught and silently converted into a fake success. The CLI's top-level
    handler converts it into ExitState.NOT_IMPLEMENTED and a machine-readable message, per the
    build spec's instruction that unimplemented commands must not pretend to work.
    """

    def __init__(self, command: str, milestone: str) -> None:
        self.command = command
        self.milestone = milestone
        super().__init__(f"{command} is not implemented yet (planned for {milestone})")
