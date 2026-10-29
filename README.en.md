# NEXORA — Streetwear Store

[English](README.en.md) | [Русский](README.md)

A portfolio e-commerce project for clothing, sneakers, and accessories. Frontend: React + TypeScript + Vite. Backend: FastAPI + PostgreSQL + SQLAlchemy 2 + Alembic.

## Run with Docker

1. Create a local `.env` file if you do not already have one:

```powershell
Copy-Item .env.example .env
```

Set a unique `JWT_SECRET` and your SMTP/OAuth settings in `.env`. Generate a random secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The application refuses to start with a missing, short, or default JWT secret. For local use, replace `POSTGRES_PASSWORD` with your own password (letters, digits, and hyphens are recommended). `.env` is passed only to the backend container and is excluded from Docker images and Git.

For YooKassa payments, set `YOOKASSA_SHOP_ID` and `YOOKASSA_SECRET_KEY` from your merchant account. Use test credentials while validating the integration. The backend creates payments using the order amount stored on the server, uses idempotency keys for payments and full refunds, and verifies incoming notifications through the YooKassa API. In the YooKassa merchant settings, configure the public HTTPS webhook URL `/api/payments/yookassa/webhook` and enable `payment.succeeded`, `payment.canceled`, `refund.succeeded`, and `refund.canceled`. Local webhook testing requires an HTTPS tunnel; do not expose the backend or secret key directly. Add `YOOKASSA_RETURN_URL` to the allowed return URLs in your YooKassa account if required.

Order acceptance is protected by the `SALES_ENABLED=false` feature flag and is disabled by default. The backend will not create orders or initiate payments until the flag is explicitly enabled after delivery has been implemented and verified. The frontend also blocks checkout.

The payment request does not include fiscal receipt data. The store owner has indicated that automatic receipts are enabled under the YooKassa agreement; verify this in both test and live accounts and confirm it matches your tax regime before accepting sales.

2. Build and start the application:

```powershell
docker compose up --build -d
```

Open the storefront at [http://localhost:8080](http://localhost:8080). Compose binds HTTP to this computer's loopback interface only. Do not remove this restriction without configuring HTTPS for external access. Database migrations are applied when the backend starts. To seed the catalog and create an administrator, run:

```powershell
docker compose exec backend python -m nexora_backend.seed
docker compose exec backend python -m nexora_backend.create_admin admin@example.com
```

For Google sign-in, add `http://localhost:8080/oauth/callback` to the allowed redirect URIs of your Google OAuth client. Email verification links also point to `http://localhost:8080`.

Useful commands:

```powershell
docker compose logs -f
docker compose stop
docker compose down
```

The database and uploaded product images are stored in Docker volumes and survive container stop/recreation. `docker compose down -v` deletes these volumes and their data. These settings are intended for development: before production, set public URLs in `.env`, use strong secrets, configure HTTPS, and set up backups.

## Run locally

1. Create the root `.env` from `.env.example`. For local Vite at `http://localhost:5173`, include that origin in `FRONTEND_ORIGINS` and set `EMAIL_VERIFICATION_BASE_URL` and the Google OAuth redirect URI to `http://localhost:5173`. For production, set `ENVIRONMENT=production`, use HTTPS for all public URLs, and provide a unique `JWT_SECRET` of at least 32 characters.
2. Apply migrations and seed the catalog:

```powershell
uv run --package nexora-backend alembic upgrade head
uv run --package nexora-backend python -m nexora_backend.seed
uv run --package nexora-backend uvicorn nexora_backend.main:app --reload --app-dir backend/src
```

3. In a second terminal, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

If `npm` is not installed, install Node.js LTS with npm first. `uv` manages only the Python dependencies.

## Frontend checks

The production build also runs the TypeScript check. Run browser end-to-end tests with:

```powershell
cd frontend
npx playwright install chromium
npm run typecheck:e2e
npm run test:e2e
```

E2E tests start a local Vite server and use isolated API responses; they do not connect to real payment or delivery providers.

## Create the first administrator

After applying migrations, create or promote an administrator. The command prompts for a password and does not print it:

```powershell
uv run --package nexora-backend python -m nexora_backend.create_admin admin@example.com
```

## Production readiness

Before making the store public:

1. Choose a domain, hosting provider, and email provider. Set public HTTPS URLs, PostgreSQL, and secrets in `.env`. Production configuration rejects HTTP URLs, SQLite, and incomplete SMTP settings.
2. Apply migrations, create a dedicated administrator, and restrict access to `/admin` at the infrastructure level if the admin panel should not be public.
3. The continuously running Docker worker checks unpaid orders every 30 seconds. By default, inventory is reserved for 30 minutes (`ORDER_RESERVATION_MINUTES`; allowed range: 5–120). A related pending payment is checked and then canceled through YooKassa before inventory is released. If the provider status is unknown, the item is not returned to stock. Run exactly one expiry worker in production and monitor its logs and alerts.
4. A full refund for a paid order can be initiated from the admin panel. Its status is confirmed through a YooKassa webhook/API call. Restocking remains a separate manual operation after the returned item is received and inspected.
5. CDEK tariff calculation, pickup-point/courier selection, labels, and tracking are **not implemented yet**. The intended scope is delivery within Russia, shipping from Moscow, with both pickup-point and courier options. You will need a CDEK contract/account and test API credentials, the sender's exact address and contact details, package dimensions/weight, verified tariffs, and end-to-end tests for creating and canceling shipments. Follow the [official CDEK API documentation](https://apidoc.cdek.ru/). Do not set `SALES_ENABLED=true` until this integration is complete and verified.
6. Confirm that your YooKassa agreement actually sends fiscal receipts automatically in both test and live modes. Agree on the tax regime, sales/delivery/return terms, consent text, and privacy policy with your accountant or legal adviser. Legal documents cannot be completed accurately without the seller's details.
7. Before external access, configure a TLS reverse proxy, dependency updates, error monitoring, alerts for worker failures, and backups of both the database and uploaded files. `scripts/backup.ps1` creates a PostgreSQL archive under `backups/`. Product images are stored separately in a Docker volume and must be copied or snapshotted independently. Periodically test a restore to a separate database.
8. Build the frontend by running `npm run build` in `frontend`. Serve `frontend/dist` over HTTPS, route `/api`, `/health`, and `/uploads` to the backend, and configure SPA fallback for `/products/{slug}`. Test at viewport widths of 360, 390, 768, and 1280 pixels.

Do not enable live sales until end-to-end YooKassa and CDEK tests pass, receipt delivery is verified, legal documents are reviewed, backup restoration is tested, and production HTTPS is configured. A domain, hosting, and test integration accounts have not yet been configured for this project; no real payments or shipments have been processed.

Migration `91d8a4c73e21` converts the old aggregate stock count into per-size inventory by splitting the total evenly and distributing any remainder to the first sizes. The total is preserved, but this is an estimate; verify the result in the admin panel against actual stock.

## API

- `GET /api/products`, `GET /api/categories` — product catalog.
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/resend-verification`, `GET /api/auth/verify-email`, `POST /api/auth/password-reset/request`, `POST /api/auth/password-reset/confirm`, `GET /api/auth/me` — email registration/verification, password reset, and JWT access after verification.
- `GET /api/cart`, `PUT /api/cart`, `POST /api/cart/items`, `PATCH/DELETE /api/cart/items/{product_id}/{size}` — user cart. `PUT /api/cart` checks current prices and stock.
- `POST /api/orders`, `GET /api/orders` — create and view orders for delivery within Russia; an order reserves stock for 30 minutes.
- `POST /api/orders/{order_id}/payment` — create or retry a YooKassa payment when credentials are configured.
- `POST /api/payments/yookassa/webhook` — verify YooKassa payment and refund notifications through the provider API.
- `POST /api/admin/orders/{order_id}/refund` — initiate a full YooKassa refund for a paid order.
- `/api/admin/*` — operations for users with the `admin` role. Inventory is tracked per size; products support galleries of up to 10 images. The admin panel accepts image URLs or JPEG, PNG, GIF, and WebP uploads up to 5 MB. Files are stored in `backend/uploads`; production needs persistent storage.
- `GET /api/admin/orders` accepts `status`, `q`, `date_from`, and `date_to` filters and returns delivery details for order processing.
- `GET /api/admin/products` returns the full catalog, including hidden products, to administrators; `PATCH /api/admin/products/{product_id}` updates a product.
- `/health`, `/health/db` — health checks.

## Tests

```powershell
uv run --package nexora-backend --group dev pytest
uv run --package nexora-backend --group dev ruff check backend/src backend/tests
uv run --package nexora-backend --group dev ruff format --check backend/src backend/tests
```

Catalog photos are example images from Unsplash; see the license and source links in `backend/src/nexora_backend/seed.py`. Before commercial use, verify the rights for each image, add your own product photos, and configure a payment provider, delivery, email notifications, and production secrets.

## Google sign-in

Email/password registration and sign-in remain available. To enable Google sign-in, create an OAuth 2.0 Client ID of type **Web application** in Google Cloud Console and add the exact callback URL to **Authorized redirect URIs**. For local development, use `http://localhost:5173/oauth/callback`. Then set these values in the root `.env`:

```dotenv
GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5173/oauth/callback
```

The frontend callback URL must match `GOOGLE_OAUTH_REDIRECT_URI`. Never commit real OAuth secrets. After changing `.env`, restart the backend and apply migrations:

```powershell
uv run --package nexora-backend alembic upgrade head
```

On the first successful Google sign-in with a verified email, a store account is created. If an account with that email already exists, Google is linked to it. Sign-in uses Authorization Code + PKCE, and the backend validates the ID token signature and claims. Real sign-in requires valid credentials and a registered callback in Google Cloud Console.

## Email verification and SMTP

After email/password registration, the customer receives a welcome email with a verification link valid for 24 hours. Sign-in and order access remain unavailable until the email is verified. After verification, a confirmation page is shown and a notification email is sent to the verified address. A new verification link can be requested from the account dialog. Google sign-in uses Google's verified email and does not require a separate verification link.

To reset a password, the customer selects **Forgot password?** on the sign-in form and enters their account email. A one-time password-reset link valid for one hour is sent to the verified address. Google-created accounts can use Google sign-in or set a password through the reset flow for the verified email. Password-reset token columns were added in migration `4d7a9b15e260`.

Configure SMTP in the root `.env`; your email provider supplies the credentials:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=shop@example.com
SMTP_USE_SSL=false
SMTP_STARTTLS=true
EMAIL_VERIFICATION_BASE_URL=http://localhost:5173
```

For SMTP port 465, typically set `SMTP_USE_SSL=true` and `SMTP_STARTTLS=false`; port 587 typically uses STARTTLS. In production, set `EMAIL_VERIFICATION_BASE_URL` to the public HTTPS store URL. Never commit your SMTP password. After changing settings, restart the backend and apply migrations:

```powershell
uv run --package nexora-backend alembic upgrade head
```

The application does not restrict recipient email domains. A single configured SMTP account can send to Gmail, Outlook/Hotmail, Yahoo, iCloud, Yandex, Mail.ru, `list.ru`, `inbox.ru`, `bk.ru`, `vk.com`, Rambler, and other providers. These settings configure the **sender account**, not customer addresses. The recipient is the email provided during registration and must be verified.

Examples of SMTP servers for sending mail through popular email providers:

| Sender provider | `SMTP_HOST` | Port | TLS settings |
|---|---|---:|---|
| Gmail / Google Workspace | `smtp.gmail.com` | 587 | `SMTP_USE_SSL=false`, `SMTP_STARTTLS=true` |
| Outlook.com / Microsoft 365 | `smtp-mail.outlook.com` | 587 | `SMTP_USE_SSL=false`, `SMTP_STARTTLS=true` |
| Yahoo Mail | `smtp.mail.yahoo.com` | 465 | `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false` |
| Yandex Mail | `smtp.yandex.ru` | 465 | `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false` |
| Mail.ru | `smtp.mail.ru` | 465 | `SMTP_USE_SSL=true`, `SMTP_STARTTLS=false` |

App-password and SMTP-access requirements vary by provider. For reliable transactional or bulk sending, prefer a dedicated email provider or your domain's SMTP service. To improve deliverability and reduce spam placement, verify the sender domain and configure the SPF, DKIM, and DMARC DNS records provided by your email provider. Delivery to a specific mailbox also depends on the recipient provider's policies and filters and cannot be guaranteed by the application.
