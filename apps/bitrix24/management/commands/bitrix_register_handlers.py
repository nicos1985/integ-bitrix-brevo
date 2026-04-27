import logging

from django.core.management.base import BaseCommand

from apps.bitrix24.models import BitrixPortal
from apps.bitrix24.install import _register_handlers

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Register Bitrix24 event handlers and bizproc activity for one or all portals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--portal",
            type=str,
            default=None,
            help="Domain of the portal to register handlers for (e.g. cliente.bitrix24.com).",
        )
        parser.add_argument(
            "--all-portals",
            action="store_true",
            default=False,
            help="Register handlers for all active portals.",
        )

    def handle(self, *args, **options):
        portal_domain = options.get("portal")
        all_portals = options.get("all_portals")

        if portal_domain:
            portals = BitrixPortal.objects.filter(domain=portal_domain, is_active=True)
        elif all_portals:
            portals = BitrixPortal.objects.filter(is_active=True)
        else:
            self.stderr.write("Provide --portal <domain> or --all-portals.")
            return

        for portal in portals:
            self.stdout.write(f"Registering handlers for {portal.domain}...")
            try:
                _register_handlers(portal)
                self.stdout.write(self.style.SUCCESS(f"  OK: {portal.domain}"))
            except Exception as exc:
                self.stderr.write(f"  ERROR {portal.domain}: {exc}")
