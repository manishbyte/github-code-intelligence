import importlib.util
import unittest

HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None


@unittest.skipUnless(HAS_PYDANTIC, "pydantic not installed")
class CodeAnalysisToolTests(unittest.TestCase):
    def test_detect_language(self):
        from app.tools.code_analysis.detect_language import DetectLanguageInput, run
        self.assertEqual(run(DetectLanguageInput(path="a/b.PY")).language, "python")
        self.assertEqual(run(DetectLanguageInput(path="Dockerfile")).method, "filename")
        self.assertEqual(run(DetectLanguageInput(path="tool", first_line="#!/usr/bin/env python3")).language, "python")
        self.assertIsNone(run(DetectLanguageInput(path="x.unknown")).language)

    def test_validate_patch_tool(self):
        from app.tools.code_analysis.validate_patch import ValidatePatchInput, run
        d = "--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"
        ok = run(ValidatePatchInput(path="m.py", original_content="a = 1\n", diff=d))
        self.assertTrue(ok.valid)
        self.assertEqual(ok.patched_content, "a = 2\n")
        bad = run(ValidatePatchInput(path="n.py", original_content="a = 1\n", diff=d))
        self.assertFalse(bad.valid)
        self.assertIsNone(bad.patched_content)

    def test_quality_checks(self):
        from app.tools.code_analysis.run_quality_checks import RunQualityChecksInput, run
        good = run(RunQualityChecksInput(path="m.py", original_content="a = 1\n", patched_content="a = 2\n"))
        self.assertTrue(good.passed)
        broken = run(RunQualityChecksInput(path="m.py", original_content="a = 1\n", patched_content="a = (\n"))
        self.assertFalse(broken.passed)
        crlf = run(RunQualityChecksInput(path="m.py", original_content="a = 1\n", patched_content="a = 2\r\n"))
        self.assertFalse(crlf.passed)
        js = run(RunQualityChecksInput(path="a.js", original_content="x\n", patched_content="y\n"))
        self.assertEqual([c.status for c in js.checks if c.name == "syntax"], ["skipped"])

    def test_line_ranges_and_secrets_tools(self):
        from app.tools.code_analysis.inspect_secrets import InspectSecretsInput, run as inspect
        from app.tools.code_analysis.validate_line_ranges import LineRangeInput, ValidateLineRangesInput, run
        res = run(ValidateLineRangesInput(content="a\nb = eval(x)\n", ranges=[LineRangeInput(start_line=2, end_line=2, evidence="eval(x)"),
                                                                           LineRangeInput(start_line=5, end_line=6, evidence="eval(x)")]))
        self.assertEqual([r.valid for r in res], [True, False])
        self.assertTrue(inspect(InspectSecretsInput(text="k = 'ghp_" + "a" * 36 + "'")).has_secrets)


if __name__ == "__main__":
    unittest.main()
