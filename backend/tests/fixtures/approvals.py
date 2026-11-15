from datetime import datetime, timedelta, timezone

from app.guardrails.action_policy import ApprovedAction, WriteActionType, payload_digest

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def make_approval(action: WriteActionType, payload: dict, *, user="u1", status="PUBLISHING", key="idem-key-0001",
                  expires=NOW + timedelta(hours=1), approved_by=None, owner="octo", repo="demo") -> ApprovedAction:
    return ApprovedAction(
        approval_id="appr-1", user_id=user, approved_by=approved_by or user, action_type=action,
        owner=owner, repo=repo, status=status, payload_digest=payload_digest(payload),
        idempotency_key=key, approved_at=NOW - timedelta(minutes=5), expires_at=expires,
    )
