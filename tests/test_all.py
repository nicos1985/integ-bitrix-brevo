import pytest
from django.test import TestCase


# ---------------------------------------------------------------
# Factories
# ---------------------------------------------------------------

def make_tenant(slug="test-tenant", name="Test Tenant"):
    from apps.tenants.models import Tenant
    return Tenant.objects.get_or_create(slug=slug, defaults={"name": name, "is_active": True})[0]


def make_brevo_account(tenant, name="Test Brevo"):
    from apps.brevo.models import BrevoAccount
    from apps.core.encryption import encrypt_value
    return BrevoAccount.objects.get_or_create(
        tenant=tenant,
        name=name,
        defaults={
            "api_key_encrypted": encrypt_value("xkeysib-test"),
            "default_sender_email": "no-reply@test.com",
            "default_sender_name": "Test",
            "webhook_secret": "secret123",
            "is_active": True,
        },
    )[0]


def make_portal(tenant, domain="test.bitrix24.com"):
    from apps.bitrix24.models import BitrixPortal
    from apps.core.encryption import encrypt_value
    return BitrixPortal.objects.get_or_create(
        domain=domain,
        defaults={
            "tenant": tenant,
            "client_id": "local.test",
            "client_secret_encrypted": encrypt_value("secret"),
            "access_token_encrypted": encrypt_value("access-token"),
            "refresh_token_encrypted": encrypt_value("refresh-token"),
            "is_active": True,
        },
    )[0]


# ---------------------------------------------------------------
# Encryption tests
# ---------------------------------------------------------------

class EncryptionTest(TestCase):
    def test_round_trip(self):
        from apps.core.encryption import encrypt_value, decrypt_value
        original = "super-secret-token-123"
        encrypted = encrypt_value(original)
        self.assertNotEqual(encrypted, original)
        decrypted = decrypt_value(encrypted)
        self.assertEqual(decrypted, original)

    def test_none_passthrough(self):
        from apps.core.encryption import encrypt_value, decrypt_value
        self.assertIsNone(encrypt_value(None))
        self.assertIsNone(decrypt_value(None))


# ---------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------

class UtilsTest(TestCase):
    def test_normalize_email(self):
        from apps.core.utils import normalize_email
        self.assertEqual(normalize_email("  Juan@Example.COM  "), "juan@example.com")
        self.assertIsNone(normalize_email(None))
        self.assertIsNone(normalize_email(""))

    def test_build_contact_hash_deterministic(self):
        from apps.core.utils import build_contact_hash
        data = {"email": "a@b.com", "name": "Test"}
        h1 = build_contact_hash(data)
        h2 = build_contact_hash(data)
        self.assertEqual(h1, h2)

    def test_build_contact_hash_differs(self):
        from apps.core.utils import build_contact_hash
        h1 = build_contact_hash({"email": "a@b.com"})
        h2 = build_contact_hash({"email": "x@y.com"})
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------
# Tenant model tests
# ---------------------------------------------------------------

class TenantModelTest(TestCase):
    def test_create_tenant(self):
        from apps.tenants.models import Tenant
        t = Tenant.objects.create(name="Acme Corp", slug="acme-corp")
        self.assertEqual(str(t), "acme-corp")
        self.assertTrue(t.is_active)


# ---------------------------------------------------------------
# Bitrix portal model tests
# ---------------------------------------------------------------

class BitrixPortalModelTest(TestCase):
    def test_create_portal(self):
        tenant = make_tenant()
        portal = make_portal(tenant)
        self.assertEqual(str(portal), "test.bitrix24.com")
        self.assertTrue(portal.is_active)

    def test_tokens_are_encrypted(self):
        from apps.core.encryption import decrypt_value
        tenant = make_tenant(slug="enc-tenant")
        portal = make_portal(tenant, domain="enc.bitrix24.com")
        self.assertNotEqual(portal.access_token_encrypted, "access-token")
        self.assertEqual(decrypt_value(portal.access_token_encrypted), "access-token")


# ---------------------------------------------------------------
# Brevo account model tests
# ---------------------------------------------------------------

class BrevoAccountModelTest(TestCase):
    def test_create_account(self):
        from apps.core.encryption import decrypt_value
        tenant = make_tenant(slug="brevo-tenant")
        account = make_brevo_account(tenant)
        self.assertEqual(decrypt_value(account.api_key_encrypted), "xkeysib-test")
        self.assertNotEqual(account.api_key_encrypted, "xkeysib-test")


# ---------------------------------------------------------------
# SyncedContact model tests
# ---------------------------------------------------------------

class SyncedContactModelTest(TestCase):
    def test_create_contact(self):
        from apps.sync.models import SyncedContact
        tenant = make_tenant(slug="sync-tenant")
        portal = make_portal(tenant, domain="sync.bitrix24.com")
        account = make_brevo_account(tenant)
        contact = SyncedContact.objects.create(
            tenant=tenant,
            bitrix_portal=portal,
            brevo_account=account,
            email="test@example.com",
            first_name="Juan",
        )
        self.assertEqual(str(contact), "test@example.com")
        self.assertEqual(contact.subscription_status, SyncedContact.SUBSCRIPTION_UNKNOWN)

    def test_unique_email_per_tenant(self):
        from django.db import IntegrityError
        from apps.sync.models import SyncedContact
        tenant = make_tenant(slug="unique-tenant")
        portal = make_portal(tenant, domain="unique.bitrix24.com")
        account = make_brevo_account(tenant, name="Unique Brevo")
        SyncedContact.objects.create(
            tenant=tenant, bitrix_portal=portal, brevo_account=account, email="dup@test.com"
        )
        with self.assertRaises(IntegrityError):
            SyncedContact.objects.create(
                tenant=tenant, bitrix_portal=portal, brevo_account=account, email="dup@test.com"
            )


# ---------------------------------------------------------------
# Brevo client tests (mocked HTTP)
# ---------------------------------------------------------------

class BrevoClientTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant(slug="brevo-client-tenant")
        self.account = make_brevo_account(self.tenant)

    def test_request_success(self):
        import responses as resp_mock
        from apps.brevo.clients import BrevoClient

        with resp_mock.RequestsMock() as rsps:
            rsps.add(resp_mock.GET, "https://api.brevo.com/v3/smtp/templates", json={"templates": []}, status=200)
            client = BrevoClient(self.account)
            result = client.request("GET", "/smtp/templates")
            self.assertEqual(result, {"templates": []})

    def test_request_404_raises(self):
        import responses as resp_mock
        from apps.brevo.clients import BrevoClient, BrevoAPIError

        with resp_mock.RequestsMock() as rsps:
            rsps.add(resp_mock.GET, "https://api.brevo.com/v3/contacts/nobody@x.com", json={"message": "Contact not found"}, status=404)
            client = BrevoClient(self.account)
            with self.assertRaises(BrevoAPIError):
                client.request("GET", "/contacts/nobody@x.com")


# ---------------------------------------------------------------
# Bitrix install handler tests
# ---------------------------------------------------------------

class BitrixInstallTest(TestCase):
    def test_install_updates_portal_tokens(self):
        """Portal must be pre-registered; install handler only fills in OAuth tokens."""
        from unittest.mock import patch
        from apps.bitrix24.install import handle_install
        from apps.core.encryption import decrypt_value

        # Pre-register the portal (as the API would do)
        tenant = make_tenant(slug="install-tenant")
        portal = make_portal(tenant, domain="install-test.bitrix24.com")

        payload = {
            "DOMAIN": "install-test.bitrix24.com",
            "member_id": "member-abc",
            "AUTH_ID": "new-access-token",
            "REFRESH_ID": "new-refresh-token",
            "PROTOCOL": "https",
        }

        with patch("apps.bitrix24.install._register_handlers"):
            result = handle_install(payload)

        self.assertEqual(result["status"], "ok")

        portal.refresh_from_db()
        self.assertEqual(portal.member_id, "member-abc")
        self.assertEqual(decrypt_value(portal.access_token_encrypted), "new-access-token")
        self.assertEqual(decrypt_value(portal.refresh_token_encrypted), "new-refresh-token")
        self.assertTrue(portal.is_active)
        self.assertIsNotNone(portal.installed_at)

    def test_install_missing_domain_raises(self):
        from apps.bitrix24.install import handle_install
        with self.assertRaises(ValueError):
            handle_install({})

    def test_install_unregistered_domain_raises(self):
        """If the portal was never pre-registered, install must raise ValueError."""
        from unittest.mock import patch
        from apps.bitrix24.install import handle_install
        with self.assertRaises(ValueError, msg="Should require pre-registration"):
            handle_install({"DOMAIN": "never-registered.bitrix24.com", "AUTH_ID": "tok"})


# ---------------------------------------------------------------
# Transactional send API test
# ---------------------------------------------------------------

class TransactionalSendAPITest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.client_user = User.objects.create_superuser("admin", "admin@test.com", "pass")
        self.tenant = make_tenant(slug="trans-tenant")
        self.portal = make_portal(self.tenant, domain="trans.bitrix24.com")
        self.account = make_brevo_account(self.tenant, name="Trans Brevo")

    def test_send_requires_auth(self):
        from django.test import Client
        c = Client()
        resp = c.post("/api/transactional/send/", {"tenant_slug": "trans-tenant"}, content_type="application/json")
        self.assertIn(resp.status_code, [401, 403])

    def test_send_validates_payload(self):
        from django.test import Client
        import json
        c = Client()
        c.login(username="admin", password="pass")
        resp = c.post(
            "/api/transactional/send/",
            json.dumps({"tenant_slug": "trans-tenant", "to_email": "not-an-email", "template_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
