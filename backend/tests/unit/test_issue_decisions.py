import unittest
from types import SimpleNamespace

from app.core.exceptions import InvalidInputError
from app.schemas.issue import IssueDraft
from app.workflows.issue_proposal.validators import (
    compose_issue_body, find_duplicates, select_findings, title_similarity, validate_issue_draft,
)

EXISTING = [(4, "Unsafe eval of user input in run()", "https://github.com/o/r/issues/4"),
            (9, "Update README badges", "https://github.com/o/r/issues/9")]


def row(i, severity="high", confidence=0.9, line=1):
    return SimpleNamespace(id=i, severity=severity, confidence=confidence, start_line=line)


class DuplicateTests(unittest.TestCase):
    def test_identical_and_reworded_titles(self):
        self.assertEqual(title_similarity("Unsafe eval", "unsafe   EVAL"), 1.0)
        dups = find_duplicates("Unsafe eval of user input in run()", EXISTING)
        self.assertEqual([d["number"] for d in dups], [4])

    def test_unrelated_title_not_duplicate(self):
        self.assertEqual(find_duplicates("Race condition in cache refresh", EXISTING), [])


class SelectionTests(unittest.TestCase):
    def test_default_orders_by_severity_then_confidence(self):
        rows = [row("a", "low"), row("b", "critical"), row("c", "high", 0.5), row("d", "high", 0.95)]
        self.assertEqual([r.id for r in select_findings(rows, None)], ["b", "d", "c", "a"])

    def test_unknown_id_is_rejected(self):
        with self.assertRaises(InvalidInputError):
            select_findings([row("a")], ["a", "zzz"])
        self.assertEqual([r.id for r in select_findings([row("a"), row("b")], ["b"])], ["b"])


class BodyTests(unittest.TestCase):
    finding = {"title": "Use of eval", "severity": "high", "category": "security", "confidence": 0.9,
               "description": "eval runs arbitrary code.", "start_line": 2, "end_line": 3, "evidence": "x = ```y```"}

    def test_body_contains_permalink_fenced_evidence_and_footer(self):
        draft = IssueDraft(title="Unsafe eval", summary="User input is evaluated.", impact="Remote code execution.")
        body = compose_issue_body(draft, [self.finding], file_path="app.py", html_url="https://github.com/o/r", commit_sha="a" * 40)
        self.assertIn(f"https://github.com/o/r/blob/{'a' * 40}/app.py#L2-L3", body)
        self.assertIn("````", body)  # fence longer than the backticks inside the evidence
        self.assertIn("approved by a human", body)

    def test_draft_with_secret_is_rejected(self):
        draft = IssueDraft(title="Leaked key", summary="Found ghp_" + "A" * 36 + " in source.", impact="Credential exposure.")
        with self.assertRaises(InvalidInputError):
            validate_issue_draft(draft)


if __name__ == "__main__":
    unittest.main()
