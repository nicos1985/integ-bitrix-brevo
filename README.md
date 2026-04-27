# Bitrix24 × Brevo — Django Integration

Django 5 + DRF backend that acts as a **Bitrix24 local app** with full Brevo contact synchronisation and transactional email support.

---

## Features

- **Multi-tenant** (logical, no schema separation).
- **Bitrix24 OAuth** install handler with encrypted token storage.
- **Bidirectional contact sync** Bitrix24 ↔ Brevo (by email).
- **Brevo marketing & transactional webhooks** (unsubscribe, delivered, etc.).
- **Bitrix24 workflow action** — "Send Brevo Email" bizproc activity.
- **Sync logs** and idempotency via `IntegrationEvent`.
- **Management commands** for bulk sync and token refresh.

---

## Quick Start

### 1. Clone and set up the environment

```bash
git clone <repo> bitrix-brevo
cd bitrix-brevo

python3.12 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Create a superuser

```bash
python manage.py createsuperuser
```

### 5. Run development server

```bash
python manage.py runserver
```

---

## API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| `GET/POST` | `/api/bitrix/install/` | Bitrix24 install handler |
| `POST` | `/api/bitrix/events/contact-add/` | onCrmContactAdd handler |
| `POST` | `/api/bitrix/events/contact-update/` | onCrmContactUpdate handler |
| `POST` | `/api/bitrix/events/app-uninstall/` | App uninstall handler |
| `POST` | `/api/bitrix/workflows/brevo-send-email/` | Workflow action executor |
| `GET` | `/api/bitrix/workflows/brevo-config/` | Template list for workflow config |
| `GET/POST` | `/api/tenants/` | Tenant management |
| `GET/PATCH` | `/api/tenants/<slug>/` | Tenant detail |
| `GET/POST` | `/api/brevo/accounts/` | Brevo account management |
| `GET` | `/api/brevo/accounts/<id>/test/` | Test Brevo API key |
| `GET` | `/api/brevo/accounts/<id>/templates/` | List Brevo templates |
| `POST` | `/api/brevo/webhooks/marketing/` | Brevo marketing webhook |
| `POST` | `/api/brevo/webhooks/transactional/` | Brevo transactional webhook |
| `POST` | `/api/transactional/send/` | Manually send transactional email |

---

## Management Commands

```bash
# Register Bitrix24 handlers for a portal
python manage.py bitrix_register_handlers --portal cliente.bitrix24.com
python manage.py bitrix_register_handlers --all-portals

# Check and refresh expiring tokens
python manage.py bitrix_refresh_tokens_check --minutes 30

# Register Brevo webhooks
python manage.py brevo_register_webhooks --account-id 1
python manage.py brevo_register_webhooks --all-accounts

# Sync contacts Bitrix24 → Brevo
python manage.py sync_bitrix_to_brevo --tenant cliente-demo --limit 500
python manage.py sync_bitrix_to_brevo --all-tenants

# Sync contacts Brevo → Bitrix24
python manage.py sync_brevo_to_bitrix --tenant cliente-demo

# Full reconciliation
python manage.py sync_reconcile --tenant cliente-demo --stale-hours 24
python manage.py sync_reconcile --all-tenants
```

---

## Initial Setup via API (Postman)

### 1. Create a tenant

```http
POST /api/tenants/
Authorization: Basic <admin>

{
  "name": "Cliente Demo",
  "slug": "cliente-demo"
}
```

### 2. Configure Brevo account

```http
POST /api/brevo/accounts/
Authorization: Basic <admin>

{
  "tenant_slug": "cliente-demo",
  "name": "Brevo Cliente Demo",
  "api_key": "xkeysib-...",
  "default_sender_email": "no-reply@cliente.com",
  "default_sender_name": "Cliente Demo",
  "webhook_secret": "my-random-secret"
}
```

### 3. Test Brevo connection

```http
GET /api/brevo/accounts/1/test/
```

### 4. Install Bitrix24 local app

In Bitrix24 → Developer Resources → Create Local App:
- Install URL: `https://your-domain.com/api/bitrix/install/`
- Scopes: `crm`, `bizproc`, `placement`, `user`

---

## Cron jobs (production)

```cron
*/15 * * * * /opt/bitrix-brevo/venv/bin/python /opt/bitrix-brevo/manage.py sync_reconcile --all-tenants >> /var/log/bitrix-brevo/reconcile.log 2>&1
0 2  * * * /opt/bitrix-brevo/venv/bin/python /opt/bitrix-brevo/manage.py bitrix_refresh_tokens_check >> /var/log/bitrix-brevo/tokens.log 2>&1
```

---

## Running Tests

```bash
pip install pytest pytest-django responses factory-boy
pytest
```

---

## Project Structure

```
bitrix_brevo_app/
├── manage.py
├── requirements.txt
├── pytest.ini
├── .env.example
├── config/
│   ├── settings/base.py · local.py · prod.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/           # encryption.py, utils.py
│   ├── tenants/        # Tenant model, API
│   ├── bitrix24/       # BitrixPortal, client, OAuth, install, workflows
│   ├── brevo/          # BrevoAccount, client, contacts, transactional, webhooks
│   ├── sync/           # SyncedContact, SyncLog, IntegrationEvent, SyncService
│   └── transactional/  # TransactionalEmailLog, send API
└── tests/
    └── test_all.py
```

---

## Security Notes

- Tokens and API keys are **never logged** — only encrypted values are stored.
- Brevo webhooks are validated by `?secret=` query parameter per account.
- Bitrix24 event handlers validate `member_id` / `domain` to resolve portals.
- All sensitive fields encrypted with **Fernet** (AES-128-CBC + HMAC-SHA256).
