"""
The cross-team bug workflow, in one file.

    Support raises  ->  Testing reproduces  ->  Development fixes
                            ^                        |
                            +------------------------+
                            |
                            v  (verified)
                        Support resolves

Every rule about who may do what lives here. The API layer asks this module and
enforces the answer; the UI renders buttons FROM the answer. That way the UI can
never offer an action the server would refuse — the two can't drift.
"""
from dataclasses import dataclass
from typing import Optional

from .models import HandoffAction, TeamKind, TicketStatus


@dataclass(frozen=True)
class ActionSpec:
    action: HandoffAction
    label: str                    # what the button says
    target_kind: Optional[TeamKind]  # None = route back to the reporter
    note_required: bool
    resulting_status: TicketStatus


# Which team may hold the ticket next, and what the button is called.
#
# Testing appears twice with DIFFERENT options depending on WHY they have it:
# a fresh ticket is being reproduced; a returned fix is being verified. The
# server tells them apart from the action of the handoff that gave them custody
# (see available_actions) — no extra column needed.

_TESTING_FIRST_PASS = [
    ActionSpec(
        HandoffAction.FORWARDED,
        "Confirm bug → forward to Development",
        TeamKind.DEVELOPMENT,
        note_required=False,
        resulting_status=TicketStatus.IN_PROGRESS,
    ),
    ActionSpec(
        HandoffAction.RETURNED_NOT_REPRODUCIBLE,
        "Not reproducible → return to Support",
        None,
        # A bug bounced back with no explanation is the single most infuriating
        # thing in a support queue.
        note_required=True,
        resulting_status=TicketStatus.TODO,
    ),
]

_TESTING_VERIFYING = [
    ActionSpec(
        HandoffAction.VERIFIED_RETURNED_TO_REPORTER,
        "Verified → return to Support",
        None,
        note_required=False,
        resulting_status=TicketStatus.CODE_REVIEW,
    ),
    ActionSpec(
        HandoffAction.RETURNED_STILL_BROKEN,
        "Still broken → send back to Development",
        TeamKind.DEVELOPMENT,
        note_required=True,   # the developer needs to know what still fails
        resulting_status=TicketStatus.IN_PROGRESS,
    ),
]

_DEVELOPMENT = [
    ActionSpec(
        HandoffAction.FIXED_RETURNED_TO_TESTING,
        "Fixed → send to Testing",
        TeamKind.TESTING,
        note_required=True,   # "what did you actually change?"
        resulting_status=TicketStatus.CODE_REVIEW,
    ),
]

_SUPPORT = [
    ActionSpec(
        HandoffAction.RESOLVED,
        "Mark Resolved",
        None,
        note_required=False,
        # Done also stamps resolved_at, which stops the SLA clock.
        resulting_status=TicketStatus.DONE,
    ),
]

# The initial raise. Support (or anyone raising) sends it to Testing.
RAISE_SPEC = ActionSpec(
    HandoffAction.RAISED,
    "Raise → send to Testing",
    TeamKind.TESTING,
    note_required=False,
    resulting_status=TicketStatus.TODO,
)


def available_actions(ticket, viewer) -> list[ActionSpec]:
    """What may THIS person do to THIS ticket, right now.

    The single source of truth for both the API's permission check and the UI's
    buttons. Returns [] when the viewer isn't the holder — which is the answer,
    not an error.
    """
    # Not in the workflow at all (every ticket predating this feature).
    if ticket.current_team_id is None:
        return []

    # Already closed: the chain is over.
    if ticket.status == TicketStatus.DONE:
        return []

    # You may act only if the ticket is with you, or with your team. Being on
    # the right team but not the named person is still allowed — otherwise one
    # tester going on holiday strands the ticket.
    is_assignee = ticket.assignee_id == viewer.id
    is_on_holding_team = viewer.team_id is not None and viewer.team_id == ticket.current_team_id
    if not (is_assignee or is_on_holding_team):
        return []

    kind = ticket.current_team.kind if ticket.current_team else None

    if kind == TeamKind.DEVELOPMENT:
        return _DEVELOPMENT

    if kind == TeamKind.SUPPORT:
        # Support can only close it once it has actually come back to them.
        return _SUPPORT

    if kind == TeamKind.TESTING:
        return _TESTING_VERIFYING if _is_verifying_a_fix(ticket) else _TESTING_FIRST_PASS

    # A team of kind OTHER holds it: no workflow actions defined. Deliberately
    # empty rather than a crash — teams are extensible.
    return []


def _is_verifying_a_fix(ticket) -> bool:
    """Testing has this because a developer sent a fix back, not because it's new.

    Derived from the last handoff rather than a stored flag: a flag would be one
    more thing that can disagree with the chain.
    """
    if not ticket.handoffs:
        return False
    last = ticket.handoffs[-1]
    return last.action == HandoffAction.FIXED_RETURNED_TO_TESTING.value


def find_spec(ticket, viewer, action: HandoffAction) -> Optional[ActionSpec]:
    """The action the viewer is attempting, IF it's one they're allowed."""
    for spec in available_actions(ticket, viewer):
        if spec.action == action:
            return spec
    return None
