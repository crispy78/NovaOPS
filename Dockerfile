FROM python:3.13-slim

# System deps
RUN apt-get update -qq && apt-get install -y -qq \
    nodejs npm sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Node dependencies (Tailwind CSS build)
COPY package.json postcss.config.js tailwind.config.js ./
RUN npm ci --silent

# Copy source
COPY . .

# Build CSS
RUN npm run build:css

# Collect static files
RUN DJANGO_SECRET_KEY=build-placeholder python manage.py collectstatic --no-input --quiet

EXPOSE 8000

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
