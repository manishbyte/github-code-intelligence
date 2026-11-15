import unittest
import uuid
from types import SimpleNamespace

from app.authorization.policies import is_allowed, require
from app.authorization.roles import WorkspaceRole, workspace_role_at_least
from app.core.exceptions import InvalidInputError, NotFoundError, PermissionDeniedError
from app.core.permissions import ensure_owner, require_admin_role
from app.guardrails.sql_and_data_safety import clamp_page, escape_like, parse_uuid, safe_sort_column

ALICE, BOB = uuid.uuid4(), uuid.uuid4()


class OwnershipTests(unittest.TestCase):
    def test_owner_gets_resource(self):
        res = SimpleNamespace(user_id=ALICE)
        self.assertIs(ensure_owner(res, ALICE), res)

    def test_other_user_or_missing_resource_looks_like_not_found(self):
        for res in (SimpleNamespace(user_id=ALICE), None, SimpleNamespace()):
            with self.assertRaises(NotFoundError):
                ensure_owner(res, BOB, "Repository")

    def test_not_found_message_does_not_reveal_existence(self):
        with self.assertRaises(NotFoundError) as cm:
            ensure_owner(SimpleNamespace(user_id=ALICE), BOB, "Approval")
        self.assertEqual(str(cm.exception), "Approval not found.")


class RolePolicyTests(unittest.TestCase):
    def test_evaluation_access_by_role(self):
        self.assertTrue(is_allowed("admin", "evaluation:run"))
        self.assertFalse(is_allowed("recruiter", "evaluation:run"))
        self.assertTrue(is_allowed("recruiter", "evaluation:read"))
        self.assertFalse(is_allowed("user", "evaluation:read"))
        self.assertFalse(is_allowed("nonsense", "evaluation:read"))
        self.assertFalse(is_allowed("admin", "unknown:action"))

    def test_require_raises(self):
        with self.assertRaises(PermissionDeniedError):
            require("user", "evaluation:run")
        with self.assertRaises(PermissionDeniedError):
            require_admin_role("recruiter")
        require_admin_role("admin")

    def test_workspace_role_ordering(self):
        self.assertTrue(workspace_role_at_least("owner", WorkspaceRole.MEMBER))
        self.assertFalse(workspace_role_at_least("viewer", WorkspaceRole.MEMBER))
        self.assertFalse(workspace_role_at_least("bogus", WorkspaceRole.VIEWER))


class DataSafetyTests(unittest.TestCase):
    def test_uuid_and_sort_and_paging(self):
        self.assertEqual(parse_uuid(str(ALICE)), ALICE)
        with self.assertRaises(InvalidInputError):
            parse_uuid("1; DROP TABLE users")
        self.assertEqual(safe_sort_column("created_at; DROP", {"created_at", "name"}, "name"), "name")
        self.assertEqual(safe_sort_column("created_at", {"created_at", "name"}, "name"), "created_at")
        self.assertEqual(clamp_page(10_000, -5), (100, 0))
        self.assertEqual(clamp_page(None, None), (20, 0))
        self.assertEqual(escape_like("50%_off\\"), "50\\%\\_off\\\\")


if __name__ == "__main__":
    unittest.main()
