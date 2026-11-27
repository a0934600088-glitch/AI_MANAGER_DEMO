import unittest
from fastapi import HTTPException
from app import auth


class AuthenticationPrimitiveTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        first = auth._password_hash("correct horse battery staple")
        second = auth._password_hash("correct horse battery staple")
        self.assertNotEqual(first, second)
        self.assertTrue(auth._password_matches("correct horse battery staple", first))
        self.assertFalse(auth._password_matches("wrong password", first))

    def test_password_hash_rejects_malformed_values(self):
        self.assertFalse(auth._password_matches("anything", "not-a-hash"))

    def test_roles_are_explicit_and_fail_closed(self):
        self.assertEqual(auth.require_role({"role": "super_admin"}, "super_admin")["role"], "super_admin")
        with self.assertRaises(HTTPException) as error:
            auth.require_role({"role": "manager"}, "super_admin")
        self.assertEqual(error.exception.status_code, 403)

    def test_staff_roles_exclude_global_admin(self):
        self.assertEqual(auth.ROLES, {"super_admin", "shop_admin", "manager", "observer"})


if __name__ == "__main__":
    unittest.main()
