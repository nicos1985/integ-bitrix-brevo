import logging

from django.core.management.base import BaseCommand

from apps.bitrix24.models import BitrixPortal
from apps.brevo.models import BrevoAccount
from apps.sync.services import SyncService
from apps.core.utils import normalize_email

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Batch-sync contacts from Bitrix24 to Brevo for a tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default=None, help="Tenant slug.")
        parser.add_argument("--all-tenants", action="store_true", default=False)
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--portal-id", type=int, default=None)

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant
        from apps.bitrix24.clients import BitrixClient

        tenant_slug = options.get("tenant")
        all_tenants = options.get("all_tenants")
        limit = options["limit"]
        portal_id = options.get("portal_id")

        if tenant_slug:
            tenants = Tenant.objects.filter(slug=tenant_slug, is_active=True)
        elif all_tenants:
            tenants = Tenant.objects.filter(is_active=True)
        else:
            self.stderr.write("Provide --tenant <slug> or --all-tenants.")
            return

        for tenant in tenants:
            portals_qs = tenant.bitrix_portals.filter(is_active=True)  # type: ignore[attr-defined]
            if portal_id:
                portals_qs = portals_qs.filter(pk=portal_id)

            for portal in portals_qs:
                brevo_account = tenant.brevo_accounts.filter(is_active=True).first()  # type: ignore[attr-defined]
                if not brevo_account:
                    self.stderr.write(f"  No Brevo account for tenant {tenant.slug}. Skipping.")
                    continue

                self.stdout.write(f"Syncing portal {portal.domain} → Brevo...")
                client = BitrixClient(portal)
                svc = SyncService(portal, brevo_account)
                synced = 0
                errors = 0
                start = 0

                while True:
                    try:
                        contacts, next_start = client.list_contacts(start=start, limit=min(limit, 50))
                    except Exception as exc:
                        self.stderr.write(f"  Error fetching contacts from Bitrix: {exc}")
                        break

                    if not contacts:
                        break

                    for bc in contacts:
                        email_list = bc.get("EMAIL") or []
                        email = None
                        for item in (email_list if isinstance(email_list, list) else []):
                            val = normalize_email(item.get("VALUE", ""))
                            if val:
                                email = val
                                break
                        if not email:
                            continue

                        try:
                            svc._sync_bitrix_contact_to_brevo(bc)
                            synced += 1
                        except Exception as exc:
                            errors += 1
                            logger.error("Error syncing contact %s: %s", bc.get("ID"), exc)

                        if synced >= limit:
                            break

                    if not next_start or synced >= limit:
                        break
                    start = next_start

                self.stdout.write(self.style.SUCCESS(
                    f"  Done. Synced: {synced}, Errors: {errors}"
                ))
