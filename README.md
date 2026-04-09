# NovaOPS

A modern CRM and operations platform built with Django 5.2, Tailwind CSS, and SQLite.

**Features:** Product catalog · Sales pipeline (Cart → Quote → Order → Invoice → Shipment) · CRM (Organisations & Contacts) · Asset tracking · Contracts · Inventory · Audit log

---

## Quick start (Docker)

The fastest way to run NovaOPS locally — no Python or Node required.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac, Windows, Linux)

```bash
git clone https://github.com/crispy78/NovaOPS.git
cd NovaOPS
make up
```

Then open **http://localhost:8000** and log in with:

| Field    | Value                  |
|----------|------------------------|
| Email    | `admin@novaops.local`  |
| Password | `novaops123`           |

Demo data is loaded automatically on first start.

### Other commands

```bash
make logs    # live application logs
make shell   # Django management shell
make demo    # reload demo data
make down    # stop the application
make reset   # wipe all data and start fresh
```

---

## Configuration

All settings live in `.env` (auto-created from `.env.example` on first `make up`).

| Variable            | Default                | Description                                      |
|---------------------|------------------------|--------------------------------------------------|
| `DJANGO_SECRET_KEY` | *(must change)*        | Django secret key — generate with `secrets.token_urlsafe(60)` |
| `DJANGO_DEBUG`      | `true`                 | Set `false` in production                        |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames                      |
| `DJANGO_SSL_REDIRECT` | `false`              | Set `true` when running behind HTTPS             |
| `ADMIN_EMAIL`       | `admin@novaops.local`  | Initial admin account email                      |
| `ADMIN_PASSWORD`    | `novaops123`           | Initial admin account password                   |
| `LOAD_DEMO_DATA`    | `true`                 | Load demo data on startup                        |
| `PORT`              | `8000`                 | Host port to expose                              |

---

## Server installation (Ubuntu 24.04 / 25.10)

For a production VPS deployment with Nginx + systemd + optional Let's Encrypt:

```bash
git clone https://github.com/crispy78/NovaOPS.git
cd NovaOPS
bash install.sh
```

The installer will prompt for your domain, admin credentials, and SSL preference, then configure everything automatically.

---

## Local development (without Docker)

```bash
git clone https://github.com/crispy78/NovaOPS.git
cd NovaOPS

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
npm install && npm run build:css

python manage.py migrate
python manage.py createsuperuser
python manage.py create_demo_data   # optional
python manage.py runserver
```

For live CSS changes during template work: `npm run watch:css`

---

## Tech stack

- **Backend:** Django 5.2, Python 3.13, SQLite
- **Frontend:** Tailwind CSS 3.4, server-rendered templates
- **Production:** Gunicorn, Nginx, systemd, Let's Encrypt
