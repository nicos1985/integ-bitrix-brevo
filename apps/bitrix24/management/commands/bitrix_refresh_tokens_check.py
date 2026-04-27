import logging
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from apps.bitrix24.models import BitrixPortal
from apps.bitrix24.oauth import BitrixOAuthService, BitrixOAuthError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check and refresh expiring Bitrix24 access tokens."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=30,
            help="Refresh tokens expiring within this many minutes (default: 30).",
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        from django.utils import timezone as dj_tz
        from datetime import timedelta

        cutoff = dj_tz.now() + timedelta(minutes=minutes)
        portals = BitrixPortal.objects.filter(
            is_active=True,
            token_expires_at__lte=cutoff,
        )
        self.stdout.write(f"Found {portals.count()} portal(s) with tokens expiring within {minutes} minutes.")
        service = BitrixOAuthService()
        for portal in portals:
            try:
                service.refresh_access_token(portal)
                self.stdout.write(self.style.SUCCESS(f"  Refreshed: {portal.domain}"))
            except BitrixOAuthError as exc:
                self.stderr.write(f"  ERROR {portal.domain}: {exc}")
