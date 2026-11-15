import unittest

from app.guardrails.evidence_validation import LineRangeCheck, validate_line_range

SRC = "def f():\n    x = eval(user)\n    return x\n"


class EvidenceTests(unittest.TestCase):
    def v(self, s, e, ev="eval(user)", **kw):
        return validate_line_range(SRC, LineRangeCheck(s, e, ev), **kw)

    def test_valid(self):
        self.assertTrue(self.v(2, 2).valid)
        self.assertTrue(self.v(1, 3, "x  =  eval(user)").valid)  # whitespace-insensitive

    def test_invalid(self):
        for args in [(0, 1), (3, 2), (2, 9), (1, 1), (3, 3)]:
            self.assertFalse(self.v(*args).valid, args)
        self.assertFalse(self.v(2, 2, None).valid)
        self.assertTrue(self.v(2, 2, None, require_evidence=False).valid)
        self.assertFalse(self.v(2, 2, "ab").valid)
        self.assertFalse(validate_line_range("", LineRangeCheck(1, 1, "abc")).valid)


if __name__ == "__main__":
    unittest.main()
