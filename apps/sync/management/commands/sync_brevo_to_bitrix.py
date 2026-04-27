import logging

from django.core.management.base import BaseCommand

from apps.sync.services import SyncService
from apps.brevo.contacts import BrevoContactService
from apps.core.utils import normalize_email

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Batch-sync contacts from Brevo to Bitrix24 for a tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default=None, help="Tenant slug.")
        parser.add_argument("--all-tenants", action="store_true", default=False)
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant

        tenant_slug = options.get("tenant")
        all_tenants = options.get("all_tenants")
        limit = options["limit"]

        if tenant_slug:
            tenants = Tenant.objects.filter(slug=tenant_slug, is_active=True)
        elif all_tenants:
            tenants = Tenant.objects.filter(is_active=True)
        else:
            self.stderr.write("Provide --tenant <slug> or --all-tenants.")
            return

        for tenant in tenants:
            portal = tenant.bitrix_portals.filter(is_active=True).first()  # type: ignore[attr-defined]
            brevo_account = tenant.brevo_accounts.filter(is_active=True).first()  # type: ignore[attr-defined]

            if not portal or not brevo_account:
                self.stderr.write(f"  Skipping tenant {tenant.slug}: missing portal or Brevo account.")
                continue

            self.stdout.write(f"Syncing Brevo → Bitrix for tenant {tenant.slug}...")
            brevo_svc = BrevoContactService(brevo_account)
            sync_svc = SyncService(portal, brevo_account)

            synced = 0
            errors = 0
            offset = 0

            while True:
                contacts = brevo_svc.list_all_contacts(limit=min(limit, 500), offset=offset)
                if not contacts:
                    break

                for bc in contacts:
                    email = normalize_email(bc.get("email", ""))
                    if not email:
                        continue
                    try:
                        from apps.sync.models import SyncedContact
                        contact, _ = SyncedContact.objects.get_or_create(
                            tenant=tenant,
                            email=email,
                            defaults={
                                "bitrix_portal": portal,
                                "brevo_account": brevo_account,
                            },
                        )
                        # Only push to Bitrix if no Bitrix ID yet
                        if not contact.bitrix_contact_id:
                            sync_svc.sync_contact_brevo_to_bitrix(contact)
                            synced += 1
                    except Exception as exc:
                        errors += 1
                        logger.error("Error syncing Brevo contact %s: %s", email, exc)

                    if synced >= limit:
                        break

                if len(contacts) < 500 or synced >= limit:
                    break
                offset += 500

            self.stdout.write(self.style.SUCCESS(
                f"  Done. Synced: {synced}, Errors: {errors}"
            ))
