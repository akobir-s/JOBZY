# JOBZY

A REST API backend for a local services marketplace. JOBZY connects clients who
need work done with verified professionals who provide it, and handles the full
lifecycle of that relationship: discovery, scheduling, booking, payment,
messaging and reviews.

Built with Django 5.2, Django REST Framework and Django Channels.

## Live API

| Resource | URL |
| --- | --- |
| API base | `https://62-238-33-236.sslip.io/` |
| Swagger UI | https://62-238-33-236.sslip.io/swagger/ |
| ReDoc | https://62-238-33-236.sslip.io/redoc/ |
| OpenAPI schema | https://62-238-33-236.sslip.io/swagger.json |
| Django admin | https://62-238-33-236.sslip.io/admin/ |
| Chat WebSocket | `wss://62-238-33-236.sslip.io/ws/chat/<room>/?token=<access>` |

HTTP redirects to HTTPS. The certificate is issued by Let's Encrypt and renews
automatically.

The hostname resolves to the server's IP through `sslip.io`, a free wildcard DNS
service, because certificate authorities cannot issue certificates for bare IP
addresses. Pointing a real domain at the server later is a DNS record plus one
`certbot --nginx -d yourdomain.com` run.

---

## Contents

- [What the platform does](#what-the-platform-does)
- [Architecture](#architecture)
- [Data model](#data-model)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [WebSocket chat](#websocket-chat)
- [Running the tests](#running-the-tests)
- [Deployment](#deployment)
- [Project layout](#project-layout)

---

## What the platform does

JOBZY has three kinds of users, all backed by a single custom `User` model.

**Clients** browse a public catalogue of services, filter by category, price and
rating, view a professional's profile and open availability, then book a time
slot. After the work is done they pay and leave a review.

**Professionals** are clients who have additionally created a professional
profile. They publish services with pricing and duration, define availability
slots on their calendar, and then confirm, complete or cancel incoming bookings.
Their public rating and completed-job count are maintained automatically by the
system rather than being self-reported.

**Administrators** get a platform-wide analytics endpoint covering user growth,
booking volume, revenue, top performers and basic system health signals, plus an
audit log of moderation actions.

### The booking lifecycle

A booking moves through an explicit state machine, and each transition is
permission-checked and generates a notification for the other party.

```
                  client books a slot
                          |
                          v
                      PENDING  ---------------------+
                          |                         |
       professional confirms                        |
                          |                         |  either party cancels
                          v                         |  (frees the slot again)
                     CONFIRMED  --------------------+
                          |                         |
     professional completes                         v
                          |                     CANCELLED
                          v
                     COMPLETED
                          |
                          v
              client may leave one review
```

Rules the API enforces:

- A slot cannot be double-booked, and cancelling a booking releases its slot.
- Only the professional who owns the booking may confirm or complete it.
- Only a completed booking can be reviewed, and only once, by the client who
  made it.
- A professional's `average_rating` and `total_reviews` are recomputed from the
  review table on every write, so editing or deleting a review keeps the
  aggregate correct.
- `total_completed_jobs` is derived from bookings in the `COMPLETED` state.

---

## Architecture

| Layer | Choice | Notes |
| --- | --- | --- |
| Framework | Django 5.2 | Single app, `users` |
| API | Django REST Framework 3.16 | ViewSets plus explicit `APIView`s |
| Auth | SimpleJWT 5.5 | Access and refresh tokens, with blacklisting on logout |
| Realtime | Django Channels 4.2 over Redis | Private chat via WebSocket |
| Filtering | django-filter 25.1 | Search, ordering and field filters on list endpoints |
| Docs | drf-yasg 1.21 | Swagger UI and ReDoc, generated from the code |
| Database | SQLite | Adequate for current load; see [Scaling notes](#scaling-notes) |
| Static files | WhiteNoise | Serves Swagger UI and admin assets from the app process |
| ASGI server | Daphne | Required because of WebSocket support |

JWT access tokens carry `username`, `is_admin` and `is_professional` as custom
claims, so the frontend can drive role-based routing without an extra round
trip.

---

## Data model

```
User (custom, AUTH_USER_MODEL)
 |
 +--1:1--> ProfessionalProfile
 |            |
 |            +--1:N--> ProfessionalService --N:1--> ServiceCategory (self-nesting tree)
 |            +--1:N--> AvailabilitySlot
 |            +--1:N--> Review
 |
 +--1:N--> Booking (as client) --N:1--> ProfessionalProfile
 |            |                          ProfessionalService
 |            |                          AvailabilitySlot
 |            +--1:1--> Payment
 |            +--1:1--> Review
 |
 +--1:N--> Message (as sender / recipient)
 +--1:N--> Notification
 +--1:N--> AdminLog (as admin)
```

Notable field-level details:

- `User.phone` is unique and required; `username` is the login identifier.
- `User.previous_login` retains the prior sign-in timestamp so the UI can show
  "last seen", since Django overwrites `last_login` on every login.
- `ProfessionalService` supports either a `fixed_price` or a
  `min_price`/`max_price` range.
- `ServiceCategory.parent` is a self-referencing FK, so categories nest.
- `Notification.link` stores an app-relative path such as `/bookings/12/` for the
  frontend to route on.

---

## Getting started

Requires Python 3.10 or newer and a running Redis instance (only needed for the
chat WebSocket; the REST API works without it).

```bash
git clone https://github.com/akob1r21/JOBZY.git
cd JOBZY

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# paste the result into DJANGO_SECRET_KEY in .env

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The API is then available at `http://127.0.0.1:8000/`, with interactive docs at
`http://127.0.0.1:8000/swagger/`.

To exercise the WebSocket chat locally, run under Daphne instead:

```bash
daphne -b 127.0.0.1 -p 8000 server.asgi:application
```

---

## Configuration

All configuration is read from environment variables, loaded from a `.env` file
in the project root. `.env` is git-ignored; `.env.example` documents every
setting.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure dev key | Cryptographic signing key. Must be set in production. |
| `DJANGO_DEBUG` | `True` | Never enable in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Browser origins allowed to call the API. |
| `DJANGO_CORS_ALLOW_ALL` | `False` | Bypasses the allow-list. Demo environments only. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Required for the admin and browsable API over HTTPS. |
| `REDIS_HOST` / `REDIS_PORT` | `127.0.0.1` / `6379` | Channels layer backend. |
| `DJANGO_DB_PATH` | `BASE_DIR/db.sqlite3` | SQLite file location. |
| `DJANGO_MEDIA_ROOT` | `BASE_DIR/media` | Uploaded avatars and service images. |
| `DJANGO_STATIC_ROOT` | `BASE_DIR/staticfiles` | `collectstatic` output. |
| `DJANGO_LOG_LEVEL` | `INFO` | Root logger level. |

When `DJANGO_DEBUG` is off, the project automatically enables secure session and
CSRF cookies, `X-Frame-Options: DENY`, content-type nosniff, and trusts the
`X-Forwarded-Proto` header from the reverse proxy.

---

## API reference

Interactive documentation is generated from the source and is the authoritative
reference:

- Swagger UI: `/swagger/`
- ReDoc: `/redoc/`
- Raw OpenAPI 2.0 schema: `/swagger.json`

### Authentication

Obtain a token pair, then send the access token as a bearer token on every
subsequent request.

```bash
curl -X POST https://<host>/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username": "alice", "password": "StrongPass123"}'
```

```json
{
  "user": { "id": 1, "username": "alice", "phone": "+992900000001", "avatar": null },
  "refresh": "eyJhbGciOi...",
  "access": "eyJhbGciOi..."
}
```

```bash
curl https://<host>/user-profile/ -H 'Authorization: Bearer <access>'
```

In Swagger UI, click **Authorize** and enter `Bearer <access_token>`.

Access tokens are valid for 24 hours and refresh tokens for 30 days. Refresh
tokens rotate on use, and the old one is blacklisted. `POST /logout/`
blacklists the supplied refresh token immediately.

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/register/` | Public | Create an account, returns a token pair |
| POST | `/login/` | Public | Authenticate, returns a token pair |
| POST | `/logout/` | Bearer | Blacklist the given refresh token |
| POST | `/api/token/` | Public | SimpleJWT token pair |
| POST | `/api/token/refresh/` | Public | Exchange a refresh token for a new pair |

### Public discovery

No authentication required. These are the endpoints a visitor browsing the site
will hit.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/search/professionals/` | Search and filter professionals |
| GET | `/search/professionals/{id}/` | Full public profile, including contact details |
| GET | `/public-services/` | Browse the service catalogue |
| GET | `/public-services/{id}/` | Service detail with the provider's summary |
| GET | `/service-info/{id}/` | Service detail with the provider's contact info |
| GET | `/categories/` | Category tree |
| GET | `/professionals/{id}/services/` | Services offered by one professional |
| GET | `/professionals/{id}/availability/` | That professional's free future slots |

Supported query parameters on list endpoints:

```
/search/professionals/?search=plumber&ordering=-average_rating&is_available=true
/public-services/?category=Plumbing&min_price=20&max_price=100&ordering=fixed_price
```

- `search` performs a text match across the relevant fields.
- `ordering` accepts any listed sort field; prefix with `-` for descending.
- `min_price` and `max_price` filter on `fixed_price`.

### Current user

| Method | Path | Description |
| --- | --- | --- |
| GET / PUT / DELETE | `/user-profile/` | Read, update or delete the signed-in account |
| PATCH | `/update-avatar/` | Upload an avatar (`multipart/form-data`) |
| GET | `/dashboard/` | Lightweight per-user summary |
| GET / POST / PUT / DELETE | `/my-profile/` | Manage the caller's professional profile |

`DELETE /my-profile/` deactivates the professional rather than destroying the
record, so historic bookings and reviews are preserved.

### Professional resources

Bearer token required. Each collection is scoped to the caller.

| Method | Path | Description |
| --- | --- | --- |
| GET / POST | `/services/` | The caller's own service listings |
| GET / PUT / PATCH / DELETE | `/services/{id}/` | Manage one listing |
| GET / POST | `/slots/` | Availability slots |
| GET / PUT / PATCH / DELETE | `/slots/{id}/` | Manage one slot |

### Bookings, payments and reviews

| Method | Path | Description |
| --- | --- | --- |
| GET / POST | `/bookings/` | Bookings where the caller is client or professional |
| POST | `/bookings/{id}/confirm/` | Professional accepts a pending booking |
| POST | `/bookings/{id}/complete/` | Professional marks the job finished |
| POST | `/bookings/{id}/cancel/` | Either party cancels, with an optional reason |
| GET / POST | `/payments/` | Payments on the caller's bookings |
| POST | `/payments/{id}/confirm/` | Professional confirms receipt |
| GET / POST | `/reviews/` | Reviews written by or about the caller |

Creating a payment generates a `transaction_id` server-side and leaves the
payment `PENDING` until confirmed. No real payment processor is wired up yet;
see [Scaling notes](#scaling-notes).

### Messaging and notifications

| Method | Path | Description |
| --- | --- | --- |
| GET / POST | `/messages/` | All messages the caller sent or received |
| GET | `/messages/inbox/` | Received messages only |
| GET | `/notifications/` | The caller's notifications |
| GET | `/notifications/unread_count/` | Unread badge count |
| POST | `/notifications/{id}/mark_as_read/` | Mark one as read |
| POST | `/notifications/mark_all_as_read/` | Mark all as read |

Notifications are generated automatically on booking creation, confirmation,
completion and cancellation, and on payment request and confirmation.

### Administration

Staff accounts only; non-staff receive `403`.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/admin-dashboard/` | Platform analytics, 12-month rolling window |
| GET / POST | `/admin-logs/` | Moderation audit log |
| GET | `/admin/` | Django admin interface |

`/admin-dashboard/` returns seven sections: `user_stats`, `professional_stats`,
`service_stats`, `booking_stats`, `payment_stats`, `review_stats` and
`system_health`. Time series are always returned as exactly 12 entries with
zero-filled gaps, so charts can be rendered without client-side padding.

---

## WebSocket chat

Connect to:

```
wss://<host>/ws/chat/<username_a>__<username_b>/?token=<access_token>
```

The room name is the two participants' usernames joined by a double underscore.
The server rejects the connection with code `4003` if the caller is not
authenticated or their username is not part of the room name.

Browsers cannot set an `Authorization` header on a WebSocket handshake, so the
JWT access token is passed as the `token` query parameter instead. Session
authentication also works, which is what the Django admin uses.

```javascript
const token = localStorage.getItem('access');
const socket = new WebSocket(
  `wss://62-238-33-236.sslip.io/ws/chat/alice__bob/?token=${token}`
);
socket.onmessage = (event) => console.log(JSON.parse(event.data));
socket.send(JSON.stringify({ message: 'Hello', receiver: 'bob' }));
```

Send:

```json
{ "message": "Hello", "receiver": "bob" }
```

Receive:

```json
{ "message": "Hello", "sender": "alice", "receiver": "bob" }
```

Every message is persisted to the `Message` table, so chat history remains
available through `GET /messages/`.

---

## Running the tests

```bash
python manage.py test users
```

The suite covers registration and login, token blacklisting on logout,
professional profile creation, the full booking state machine including
double-booking and slot release, review integrity and rating recalculation,
message visibility for both parties, notification counters, permission
boundaries on every public and private endpoint, and OpenAPI schema generation.

---

## Deployment

The production instance runs Daphne under systemd behind nginx, with Let's
Encrypt for TLS.

```
Internet
   |
   v
nginx :443  ----> /static/  served from /var/www/jobzy/staticfiles
                  /media/   served from /var/www/jobzy/media
                  /ws/      proxied with Upgrade headers
                  /         proxied
   |
   v
daphne 127.0.0.1:8000  (systemd unit "jobzy", user "jobzy")
   |
   +--> SQLite  /var/www/jobzy/data/db.sqlite3
   +--> Redis   127.0.0.1:6379   (Channels layer)
```

Server layout:

| Path | Contents |
| --- | --- |
| `/opt/jobzy/app` | Checked-out repository |
| `/opt/jobzy/venv` | Virtualenv |
| `/opt/jobzy/app/.env` | Production secrets, mode 600 |
| `/var/www/jobzy/data` | SQLite database |
| `/var/www/jobzy/media` | Uploaded files |
| `/var/www/jobzy/staticfiles` | `collectstatic` output |
| `/etc/systemd/system/jobzy.service` | Service unit |
| `/etc/nginx/sites-available/jobzy` | nginx site |

To ship a new version, push to `main` and then run on the server:

```bash
bash /opt/jobzy/app/deploy.sh
```

Useful operational commands:

```bash
systemctl status jobzy          # service state
journalctl -u jobzy -f          # live application logs
tail -f /var/log/nginx/jobzy.error.log
certbot renew --dry-run         # verify certificate renewal
```

Production checklist:

1. Set `DJANGO_DEBUG=False` and a strong `DJANGO_SECRET_KEY`.
2. Add the public hostname to `DJANGO_ALLOWED_HOSTS` and
   `DJANGO_CSRF_TRUSTED_ORIGINS`.
3. Add the frontend origin to `DJANGO_CORS_ALLOWED_ORIGINS`.
4. Run `python manage.py migrate` and `python manage.py collectstatic --noinput`.
5. Ensure Redis is running and reachable.
6. Serve `/media/` from nginx directly; Django only serves it when `DEBUG` is on.

nginx must forward WebSocket upgrade headers for `/ws/` and set
`X-Forwarded-Proto` so Django can detect HTTPS behind the proxy.

### Scaling notes

These are known limitations rather than defects, listed so they are not
mistaken for oversights:

- **SQLite** handles the current workload but serialises writes. Migrating to
  PostgreSQL is a settings change plus a data dump and load.
- **Payments** are recorded, not processed. Integrating a real provider means
  replacing the generated `transaction_id` with the provider's reference and
  adding a webhook to confirm settlement.
- **List endpoints return plain arrays.** Pagination is configured but disabled
  so existing clients keep working; enable `DEFAULT_PAGINATION_CLASS` in
  `server/settings.py` once the frontend can consume
  `{count, next, previous, results}`.
- **Media files** are stored on the local disk. Moving to object storage would
  be required before running more than one application server.

---

## Project layout

```
JOBZY/
├── manage.py
├── requirements.txt
├── .env.example              Documented environment variables
├── server/
│   ├── settings.py           Environment-driven configuration
│   ├── urls.py               Root URL config
│   ├── asgi.py               HTTP and WebSocket routing
│   └── wsgi.py
└── users/
    ├── models.py             All eleven domain models
    ├── serializers.py        Request and response shapes
    ├── views.py              ViewSets, APIViews and the admin dashboard
    ├── urls.py               Router registrations and explicit routes
    ├── filters.py            django-filter FilterSets
    ├── signals.py            Rating and completed-job aggregates, notifications
    ├── consumers.py          Chat WebSocket consumer
    ├── routing.py            WebSocket URL patterns
    ├── admin.py
    ├── tests.py
    └── migrations/
```

---

## License

Not currently licensed for redistribution. Contact the author for terms.

## Author

Akobir Safarov — [github.com/akob1r21](https://github.com/akob1r21)
