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

    def test_public_tenant_resolution_requires_matching_https_origin(self):
        from unittest.mock import MagicMock, patch
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = {
            "id": 27, "allowed_domains": ["shop.example.com"]
        }
        with patch.object(auth, "ensure_schema"), patch.object(auth.analytics, "_connect", return_value=connection):
            self.assertEqual(auth.resolve_public_tenant("public-key", "https://shop.example.com"), "27")
            with self.assertRaises(HTTPException) as error:
                auth.resolve_public_tenant("public-key", "https://attacker.example")
        self.assertEqual(error.exception.status_code, 403)

    def test_tenant_domain_validation_rejects_paths_and_plain_http(self):
        with self.assertRaises(HTTPException):
            auth._normalize_domain("https://shop.example.com/admin")
        with self.assertRaises(HTTPException):
            auth._normalize_domain("http://shop.example.com")
        self.assertEqual(auth._normalize_domain("SHOP.EXAMPLE.COM"), "shop.example.com")

    def test_staff_roles_exclude_global_admin(self):
        self.assertEqual(auth.ROLES, {"super_admin", "shop_admin", "manager", "observer"})


if __name__ == "__main__":
    unittest.main()
