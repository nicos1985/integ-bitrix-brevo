import logging
from datetime import datetime, timezone, timedelta

from django.core.management.base import BaseCommand

from apps.sync.models import SyncedContact
from apps.sync.services import SyncService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcile contacts between Bitrix24 and Brevo for a tenant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default=None, help="Tenant slug.")
        parser.add_argument("--all-tenants", action="store_true", default=False)
        parser.add_argument(
            "--stale-hours",
            type=int,
            default=24,
            help="Re-sync contacts not synced in this many hours.",
        )

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant

        tenant_slug = options.get("tenant")
        all_tenants = options.get("all_tenants")
        stale_hours = options["stale_hours"]

        if tenant_slug:
            tenants = Tenant.objects.filter(slug=tenant_slug, is_active=True)
        elif all_tenants:
            tenants = Tenant.objects.filter(is_active=True)
        else:
            self.stderr.write("Provide --tenant <slug> or --all-tenants.")
            return

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=stale_hours)

        for tenant in tenants:
            portal = tenant.bitrix_portals.filter(is_active=True).first()  # type: ignore[attr-defined]
            brevo_account = tenant.brevo_accounts.filter(is_active=True).first()  # type: ignore[attr-defined]

            if not portal or not brevo_account:
                self.stderr.write(f"  Skipping {tenant.slug}: missing portal or Brevo account.")
                continue

            stale = SyncedContact.objects.filter(
                tenant=tenant,
                subscription_status__in=[SyncedContact.SUBSCRIPTION_UNKNOWN, SyncedContact.SUBSCRIPTION_SUBSCRIBED],
            ).filter(
                last_synced_at__lt=cutoff
            ) | SyncedContact.objects.filter(
                tenant=tenant,
                last_synced_at__isnull=True,
            )

            self.stdout.write(f"Reconciling {stale.count()} contacts for tenant {tenant.slug}...")
            svc = SyncService(portal, brevo_account)
            synced = 0
            errors = 0

            for contact in stale:
                try:
                    svc.sync_contact_bitrix_to_brevo(contact)
                    synced += 1
                except Exception as exc:
                    errors += 1
                    logger.error("Reconcile error for %s: %s", contact.email, exc)

            self.stdout.write(self.style.SUCCESS(
                f"  Done. Synced: {synced}, Errors: {errors}"
            ))
