from __future__ import annotations

from app.evaluation.datasets import Case
from app.evaluation.metrics import CaseOutcome
from app.guardrails.secret_detection import find_secrets
from app.schemas.issue import IssueDraft
from app.workflows.issue_proposal.validators import compose_issue_body, find_duplicates, validate_issue_draft


class IssueEvaluator:
    """Deterministic evaluation of duplicate detection and issue-body assembly."""

    kind = "issue"

    async def evaluate(self, case: Case) -> CaseOutcome:
        i, exp = case.input, case.expected
        draft = validate_issue_draft(IssueDraft(title=i["title"], summary=i["summary"], impact=i["impact"], suggested_fix=i.get("suggested_fix")))
        dups = find_duplicates(draft.title, [(e["number"], e["title"], e["url"]) for e in i.get("existing_issues", [])])
        body = compose_issue_body(draft, i["findings"], file_path=i["file_path"], html_url=i["html_url"], commit_sha=i["commit_sha"])
        checks = {
            "duplicate_detection": bool(dups) == exp["duplicate"],
            "body_contains": all(s in body for s in exp.get("body_contains", [])),
            "no_secrets": not find_secrets(body),
        }
        return CaseOutcome(all(checks.values()), sum(checks.values()) / len(checks), {"checks": checks, "duplicates": [d["number"] for d in dups]})
