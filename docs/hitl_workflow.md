# Human-in-the-loop workflow

```
PENDING_REVIEW ──approve──▶ APPROVED ──publish──▶ PUBLISHING ──▶ PUBLISHED
      │                         │                      └────────▶ FAILED
      ├──reject──▶ REJECTED     └──expire──▶ EXPIRED
      └──expire──▶ EXPIRED
```

1. A workflow creates a proposal (issue or code change) and an approval request whose **payload** is the exact content
   that would be sent; its SHA-256 digest is stored.
2. The UI shows that content. Approve/Reject sends back the digest the user saw; the backend rejects the decision if it
   differs, if the request expired, or if the caller is not the owner.
3. `publish` moves `APPROVED → PUBLISHING` (committed before any GitHub call), then runs the steps:
   issue: `create_issue`; code change: preflight (artifact matches approval, file unchanged upstream) →
   `create_branch` → `create_commit` → `create_pull_request`. Each step re-verifies its approved payload, the user's
   permission, and records a ledger row; replays return the stored result instead of writing again.
4. The final state is `PUBLISHED` only if every step verified; otherwise `FAILED` (propose again).
