import logging

from django.core.management.base import BaseCommand

from apps.brevo.models import BrevoAccount

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Register webhooks in Brevo for one or all active accounts."

    def add_arguments(self, parser):
        parser.add_argument("--account-id", type=int, default=None, help="BrevoAccount PK.")
        parser.add_argument("--all-accounts", action="store_true", default=False)

    def handle(self, *args, **options):
        from django.conf import settings
        from apps.brevo.clients import BrevoClient, BrevoAPIError

        account_id = options.get("account_id")
        all_accounts = options.get("all_accounts")

        if account_id:
            accounts = BrevoAccount.objects.filter(pk=account_id, is_active=True)
        elif all_accounts:
            accounts = BrevoAccount.objects.filter(is_active=True)
        else:
            self.stderr.write("Provide --account-id <id> or --all-accounts.")
            return

        base_url = settings.BITRIX_APP_BASE_URL.rstrip("/")

        for account in accounts:
            self.stdout.write(f"Registering webhooks for Brevo account {account.pk} ({account.name})...")
            client = BrevoClient(account)
            secret = account.webhook_secret or ""

            for webhook_type, path in [
                ("marketing", f"{base_url}/api/brevo/webhooks/marketing/?secret={secret}"),
                ("transactional", f"{base_url}/api/brevo/webhooks/transactional/?secret={secret}"),
            ]:
                events_map = {
                    "marketing": ["unsubscribe", "contact_updated", "hardBounce", "softBounce", "spam", "listAddition"],
                    "transactional": ["delivered", "hardBounce", "softBounce", "blocked", "spam", "opened", "click", "unsubscribed"],
                }
                events = events_map[webhook_type]
                payload = {
                    "url": path,
                    "events": events,
                    "type": webhook_type,
                    "sendFormat": "json",
                }
                try:
                    result = client.request("POST", "/webhooks", json=payload)
                    self.stdout.write(self.style.SUCCESS(f"  Registered {webhook_type}: {result}"))
                except BrevoAPIError as exc:
                    self.stderr.write(f"  ERROR registering {webhook_type}: {exc}")
