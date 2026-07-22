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

from .models import HandoffAction, TeamKind, TicketStatus, TicketType


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

def _testing_first_pass(ticket) -> list[ActionSpec]:
    """Wording only -- same two actions either way. A Task routed through
    Testing isn't a "bug" that needs "confirming"; saying so on a plain Task
    was just confusing. Bug tickets keep the sharper, bug-specific language."""
    is_bug = ticket.ticket_type == TicketType.BUG
    return [
        ActionSpec(
            HandoffAction.FORWARDED,
            "Confirm bug → forward to Development" if is_bug else "Approve → forward to Development",
            TeamKind.DEVELOPMENT,
            note_required=False,
            resulting_status=TicketStatus.IN_PROGRESS,
        ),
        ActionSpec(
            HandoffAction.RETURNED_NOT_REPRODUCIBLE,
            "Not reproducible → return to Support" if is_bug else "Can't proceed → return to Support",
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

# The customer came back: "it's still broken". Reopening is not an edge case in
# support — it's how you find out the fix didn't work, and a tool that can't do
# it forces people into the database. Only the team that CLOSED it may reopen,
# and it goes straight back to Testing, because a fix that didn't hold has to be
# re-verified before anyone touches code again.
_SUPPORT_RESOLVED = [
    ActionSpec(
        HandoffAction.REOPENED,
        "Reopen → send back to Testing",
        TeamKind.TESTING,
        note_required=True,   # "the customer says X still happens"
        resulting_status=TicketStatus.TODO,
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
    # Not in the workflow yet. There's no "current holder" to restrict this to
    # -- anyone in the org may raise it, the same as anyone may pick a target
    # team when CREATING a ticket. This is also the path for every ticket that
    # predates the workflow feature: it doesn't strand them, it just means
    # "raising" is the only thing anyone can do to them until someone does.
    if ticket.current_team_id is None:
        return [RAISE_SPEC]

    # You may act only if the ticket is with you, or with your team. Being on
    # the right team but not the named person is still allowed — otherwise one
    # tester going on holiday strands the ticket.
    is_assignee = ticket.assignee_id == viewer.id
    is_on_holding_team = viewer.team_id is not None and viewer.team_id == ticket.current_team_id
    if not (is_assignee or is_on_holding_team):
        return []

    kind = ticket.current_team.kind if ticket.current_team else None

    # Closed — but not sealed. The team that closed it can reopen it, because
    # "the customer says it's still broken" is a normal Tuesday, not an
    # exception. Previously this returned [] and the ticket was unreachable by
    # EVERY route: handoff 403, edit 400, drag 400. Even an admin was stuck.
    if ticket.status == TicketStatus.DONE:
        return _SUPPORT_RESOLVED if kind == TeamKind.SUPPORT else []

    if kind == TeamKind.DEVELOPMENT:
        return _DEVELOPMENT

    if kind == TeamKind.SUPPORT:
        # Support can only close it once it has actually come back to them.
        return _SUPPORT

    if kind == TeamKind.TESTING:
        return _TESTING_VERIFYING if _is_verifying_a_fix(ticket) else _testing_first_pass(ticket)

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
