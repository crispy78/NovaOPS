#!/bin/sh
set -e

echo "▸ Running database migrations…"
python manage.py migrate --no-input

echo "▸ Creating admin user…"
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
email = '${ADMIN_EMAIL:-admin@novaops.local}'
password = '${ADMIN_PASSWORD:-novaops123}'
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(username=email, email=email, password=password)
    print(f'  Admin user created: {email}')
else:
    print(f'  Admin user already exists: {email}')
"

if [ "${LOAD_DEMO_DATA:-true}" = "true" ]; then
    echo "▸ Loading demo data…"
    python manage.py create_demo_data 2>/dev/null || true
fi

echo "▸ Starting Gunicorn…"
exec gunicorn \
    --workers "${GUNICORN_WORKERS:-3}" \
    --bind "0.0.0.0:8000" \
    --access-logfile - \
    --error-logfile - \
    novaops.wsgi:application
