import unittest

from app.guardrails.secret_detection import find_secrets
from app.schemas.finding import RawFinding, RawReview
from app.workflows.code_review.validators import validate_review

CONTENT = "def run(user_input):\n    result = eval(user_input)\n    return result\n"


def finding(**over):
    base = dict(category="security", severity="high", confidence=0.9, title="Use of eval",
                description="eval executes arbitrary code.", start_line=2, end_line=2, evidence="result = eval(user_input)")
    base.update(over)
    return RawFinding(**base)


def review(*findings, decision="issue"):
    return RawReview(findings=list(findings), decision=decision, reasoning="Reasoned summary.")


class ValidateReviewTests(unittest.TestCase):
    def run_validation(self, raw, content=CONTENT):
        return validate_review(raw, content=content, secret_findings=find_secrets(content))

    def test_valid_finding_is_accepted(self):
        v = self.run_validation(review(finding()))
        self.assertEqual((v.decision, len(v.findings), v.rejected), ("issue", 1, ()))

    def test_hallucinated_evidence_or_lines_are_rejected(self):
        for bad in (finding(evidence="os.system(cmd)"), finding(start_line=40, end_line=41), finding(end_line=99)):
            v = self.run_validation(review(bad))
            self.assertEqual((v.decision, len(v.findings)), ("no_issue", 0))
            self.assertEqual(len(v.rejected), 1)

    def test_decision_comes_from_validated_findings_not_the_model(self):
        v = self.run_validation(review(finding(evidence="nonexistent"), decision="issue"))
        self.assertEqual(v.decision, "no_issue")
        v2 = self.run_validation(review(finding(), decision="no_issue"))
        self.assertEqual(v2.decision, "issue")

    def test_low_confidence_and_duplicates(self):
        self.assertEqual(self.run_validation(review(finding(confidence=0.2))).findings, ())
        self.assertEqual(len(self.run_validation(review(finding(), finding())).findings), 1)

    def test_deterministic_secret_finding_is_added_without_model_help(self):
        content = "API = 'ghp_" + "Z" * 36 + "'\n"
        v = validate_review(review(decision="no_issue"), content=content.replace("Z" * 36, "[REDACTED]"), secret_findings=find_secrets(content))
        self.assertEqual([f.category for f in v.findings], ["security"])
        self.assertEqual(v.decision, "issue")
        self.assertNotIn("Z" * 36, v.findings[0].evidence)

    def test_findings_sorted_by_severity(self):
        v = self.run_validation(review(finding(severity="low", title="Minor"), finding(severity="critical", title="Major", start_line=1, end_line=1, evidence="def run(user_input):")))
        self.assertEqual([f.severity for f in v.findings], ["critical", "low"])


if __name__ == "__main__":
    unittest.main()
