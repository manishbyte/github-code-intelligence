import unittest
from datetime import datetime, timedelta, timezone
from itertools import product

from app.approvals.state_machine import (
    ApprovalEvent, ApprovalSnapshot, ApprovalState, InvalidTransitionError, TERMINAL_STATES,
    begin_publish, decide, finish_publish, next_state, to_approved_action,
)
from app.core.exceptions import ApprovalError
from app.guardrails.action_policy import WriteActionType, authorize_write, payload_digest

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
PAYLOAD = {"owner": "octo", "repo": "demo", "title": "Bug", "body": "", "labels": []}
DIGEST = payload_digest(PAYLOAD)


def snap(state=ApprovalState.PENDING_REVIEW, **kw):
    base = dict(approval_id="a1", owner_user_id="u1", state=state, payload_digest=DIGEST, expires_at=NOW + timedelta(hours=1))
    base.update(kw)
    return ApprovalSnapshot(**base)


class StateMachineTests(unittest.TestCase):
    def test_only_approved_can_start_publishing(self):
        for state, event in product(ApprovalState, ApprovalEvent):
            if event is ApprovalEvent.START_PUBLISH and state is not ApprovalState.APPROVED:
                with self.assertRaises(InvalidTransitionError):
                    next_state(state, event)
        self.assertIs(next_state(ApprovalState.APPROVED, ApprovalEvent.START_PUBLISH), ApprovalState.PUBLISHING)

    def test_terminal_states_have_no_exits(self):
        for state, event in product(TERMINAL_STATES, ApprovalEvent):
            with self.assertRaises(InvalidTransitionError):
                next_state(state, event)

    def test_publishing_cannot_be_approved_or_rejected_again(self):
        for event in (ApprovalEvent.APPROVE, ApprovalEvent.REJECT):
            with self.assertRaises(InvalidTransitionError):
                next_state(ApprovalState.PUBLISHING, event)

    def test_happy_path_and_capability(self):
        approved = decide(snap(), decider_user_id="u1", approve=True, displayed_payload_digest=DIGEST, now=NOW)
        self.assertIs(approved.state, ApprovalState.APPROVED)
        with self.assertRaises(ApprovalError):  # not yet PUBLISHING: no capability
            to_approved_action(approved, action_type=WriteActionType.CREATE_ISSUE, owner="octo", repo="demo", idempotency_key="idem-key-1")
        publishing = begin_publish(approved, now=NOW)
        action = to_approved_action(publishing, action_type=WriteActionType.CREATE_ISSUE, owner="octo", repo="demo", idempotency_key="idem-key-1")
        authorize_write(action, user_id="u1", action_type=WriteActionType.CREATE_ISSUE, owner="octo", repo="demo", payload=PAYLOAD, now=NOW)
        self.assertIs(finish_publish(publishing, succeeded=True).state, ApprovalState.PUBLISHED)
        self.assertIs(finish_publish(publishing, succeeded=False).state, ApprovalState.FAILED)

    def test_reject_blocks_publishing(self):
        rejected = decide(snap(), decider_user_id="u1", approve=False, displayed_payload_digest=DIGEST, now=NOW)
        with self.assertRaises(InvalidTransitionError):
            begin_publish(rejected, now=NOW)

    def test_decision_guards(self):
        with self.assertRaises(ApprovalError):  # someone else
            decide(snap(), decider_user_id="u2", approve=True, displayed_payload_digest=DIGEST, now=NOW)
        with self.assertRaises(ApprovalError):  # content changed after display
            decide(snap(), decider_user_id="u1", approve=True, displayed_payload_digest="0" * 64, now=NOW)
        with self.assertRaises(ApprovalError):  # expired
            decide(snap(expires_at=NOW), decider_user_id="u1", approve=True, displayed_payload_digest=DIGEST, now=NOW)
        with self.assertRaises(ApprovalError):  # naive clock
            decide(snap(), decider_user_id="u1", approve=True, displayed_payload_digest=DIGEST, now=datetime(2026, 1, 1))

    def test_double_decision_and_expired_publish_blocked(self):
        approved = decide(snap(), decider_user_id="u1", approve=True, displayed_payload_digest=DIGEST, now=NOW)
        with self.assertRaises(InvalidTransitionError):
            decide(approved, decider_user_id="u1", approve=True, displayed_payload_digest=DIGEST, now=NOW)
        with self.assertRaises(ApprovalError):
            begin_publish(approved, now=NOW + timedelta(hours=2))


if __name__ == "__main__":
    unittest.main()
