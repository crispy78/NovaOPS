#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# NovaOPS — automated installer for Ubuntu 24.04 / 25.10
# Run as a user with sudo rights:
#   bash install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}▸ $*${RESET}"; }
success() { echo -e "${GREEN}✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}⚠ $*${RESET}"; }
error()   { echo -e "${RED}✗ $*${RESET}"; exit 1; }

echo -e "${BOLD}"
echo "  ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗  ██████╗ ██████╗ ███████╗"
echo "  ████╗  ██║██╔═══██╗██║   ██║██╔══██╗██╔═══██╗██╔══██╗██╔════╝"
echo "  ██╔██╗ ██║██║   ██║██║   ██║███████║██║   ██║██████╔╝███████╗"
echo "  ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║██║   ██║██╔═══╝ ╚════██║"
echo "  ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║╚██████╔╝██║     ███████║"
echo "  ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚══════╝"
echo -e "${RESET}"
echo -e "  ${BOLD}NovaOPS Installer${RESET} — Ubuntu 24.04 / 25.10"
echo ""

# ── Preflight ─────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] && error "Do not run as root. Run as a sudo-capable user."
command -v sudo >/dev/null || error "sudo is required."

# ── Configuration prompts ─────────────────────────────────────────────────────
echo -e "${BOLD}── Configuration ─────────────────────────────────────────────────────────${RESET}"
echo ""

read -rp "  Domain or IP address (e.g. novaops.example.com or 10.25.10.164): " DOMAIN
[[ -z "$DOMAIN" ]] && error "Domain/IP is required."

read -rp "  Enable HTTPS with Let's Encrypt? Requires a public domain. [y/N]: " WANT_SSL
WANT_SSL="${WANT_SSL,,}"

read -rp "  App directory [/home/novaops/app]: " APP_DIR
APP_DIR="${APP_DIR:-/home/novaops/app}"

read -rp "  System user to run the app [novaops]: " APP_USER
APP_USER="${APP_USER:-novaops}"

read -rp "  Admin e-mail for superuser account: " ADMIN_EMAIL
[[ -z "$ADMIN_EMAIL" ]] && error "Admin e-mail is required."

read -rsp "  Admin password (hidden): " ADMIN_PASSWORD; echo ""
[[ ${#ADMIN_PASSWORD} -lt 8 ]] && error "Password must be at least 8 characters."

echo ""
echo -e "${BOLD}── Summary ───────────────────────────────────────────────────────────────${RESET}"
echo "  Domain / IP   : $DOMAIN"
echo "  HTTPS (SSL)   : $( [[ $WANT_SSL == y ]] && echo 'Yes (Let'\''s Encrypt)' || echo 'No (HTTP only)' )"
echo "  App directory : $APP_DIR"
echo "  System user   : $APP_USER"
echo "  Admin e-mail  : $ADMIN_EMAIL"
echo ""
read -rp "  Proceed? [y/N]: " CONFIRM
[[ "${CONFIRM,,}" != "y" ]] && { warn "Aborted."; exit 0; }
echo ""

# ── System packages ───────────────────────────────────────────────────────────
info "Installing system packages…"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    git nginx sqlite3 curl
[[ "${WANT_SSL,,}" == "y" ]] && sudo apt-get install -y -qq certbot python3-certbot-nginx
success "System packages installed."

# ── App user ──────────────────────────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    info "Creating system user '$APP_USER'…"
    sudo useradd -m -s /bin/bash "$APP_USER"
    success "User '$APP_USER' created."
else
    info "User '$APP_USER' already exists — skipping."
fi

# ── Clone / update repo ───────────────────────────────────────────────────────
PARENT_DIR="$(dirname "$APP_DIR")"
info "Setting up application in $APP_DIR…"
if [[ ! -d "$APP_DIR/.git" ]]; then
    sudo mkdir -p "$PARENT_DIR"
    sudo chown "$APP_USER:$APP_USER" "$PARENT_DIR"
    sudo -u "$APP_USER" git clone https://github.com/crispy78/NovaOPS.git "$APP_DIR"
    success "Repository cloned."
else
    sudo -u "$APP_USER" git -C "$APP_DIR" pull origin main
    success "Repository updated."
fi

# ── Virtual environment ───────────────────────────────────────────────────────
VENV="$APP_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
    info "Creating Python virtual environment…"
    sudo -u "$APP_USER" python3 -m venv "$VENV"
fi
info "Installing Python dependencies…"
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet --upgrade pip
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
sudo -u "$APP_USER" "$VENV/bin/pip" install --quiet gunicorn
success "Python dependencies installed."

# ── .env file ─────────────────────────────────────────────────────────────────
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    info "Generating .env file…"
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(60))")
    [[ "${WANT_SSL,,}" == "y" ]] && SSL_VAL=true || SSL_VAL=false

    sudo -u "$APP_USER" tee "$ENV_FILE" > /dev/null <<EOF
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=${DOMAIN}
DJANGO_SSL_REDIRECT=${SSL_VAL}
EOF
    sudo chmod 600 "$ENV_FILE"
    success ".env file created."
else
    warn ".env already exists — not overwritten. Review it manually if needed."
fi

# ── Directories & permissions ─────────────────────────────────────────────────
info "Setting up directories and permissions…"
sudo -u "$APP_USER" mkdir -p "$APP_DIR/media"
sudo chmod o+x "/home/$APP_USER"
sudo chmod -R o+rX "$APP_DIR/staticfiles" 2>/dev/null || true
sudo chmod -R o+rX "$APP_DIR/media"

# ── Database & static files ───────────────────────────────────────────────────
info "Running database migrations…"
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR'
    export \$(cat .env | xargs)
    '$VENV/bin/python' manage.py migrate --no-input
"
success "Migrations complete."

info "Collecting static files…"
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR'
    export \$(cat .env | xargs)
    '$VENV/bin/python' manage.py collectstatic --no-input --quiet
"
sudo chmod -R o+rX "$APP_DIR/staticfiles"
success "Static files collected."

# ── Superuser ─────────────────────────────────────────────────────────────────
info "Creating admin user…"
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR'
    export \$(cat .env | xargs)
    '$VENV/bin/python' manage.py shell -c \"
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='${ADMIN_EMAIL}').exists():
    User.objects.create_superuser(
        username='${ADMIN_EMAIL}',
        email='${ADMIN_EMAIL}',
        password='${ADMIN_PASSWORD}'
    )
    print('Superuser created.')
else:
    print('Superuser already exists — skipped.')
\"
"
success "Admin user ready."

# ── systemd service ───────────────────────────────────────────────────────────
SOCKET_DIR="/run/novaops"
SERVICE_FILE="/etc/systemd/system/novaops.service"
info "Installing systemd service…"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=NovaOPS Gunicorn daemon
After=network.target

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV}/bin/gunicorn \\
    --workers 3 \\
    --bind unix:/run/novaops/gunicorn.sock \\
    novaops.wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RuntimeDirectory=novaops
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable novaops
sudo systemctl restart novaops
success "Gunicorn service started."

# ── Nginx ─────────────────────────────────────────────────────────────────────
NGINX_CONF="/etc/nginx/sites-available/novaops"
info "Configuring Nginx…"
sudo tee "$NGINX_CONF" > /dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    client_max_body_size 20M;

    location /static/ {
        alias ${APP_DIR}/staticfiles/;
    }

    location /media/ {
        alias ${APP_DIR}/media/;
    }

    location / {
        proxy_pass http://unix:/run/novaops/gunicorn.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/novaops
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t
sudo systemctl reload nginx
success "Nginx configured."

# ── Firewall ──────────────────────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    info "Configuring firewall…"
    sudo ufw allow 'Nginx Full' --quiet
    sudo ufw allow OpenSSH --quiet
    sudo ufw --force enable --quiet 2>/dev/null || true
    success "Firewall updated."
fi

# ── HTTPS / Let's Encrypt ─────────────────────────────────────────────────────
if [[ "${WANT_SSL,,}" == "y" ]]; then
    info "Obtaining SSL certificate from Let's Encrypt…"
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$ADMIN_EMAIL"
    success "SSL certificate installed."

    info "Updating .env for HTTPS…"
    sudo -u "$APP_USER" sed -i \
        's/^DJANGO_SSL_REDIRECT=.*/DJANGO_SSL_REDIRECT=true/' "$ENV_FILE"
    sudo systemctl restart novaops
    success ".env updated for HTTPS."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  NovaOPS installed successfully!${RESET}"
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════${RESET}"
echo ""
SCHEME=$( [[ "${WANT_SSL,,}" == "y" ]] && echo "https" || echo "http" )
echo -e "  URL      : ${BOLD}${SCHEME}://${DOMAIN}${RESET}"
echo -e "  Admin    : ${ADMIN_EMAIL}"
echo -e "  App dir  : ${APP_DIR}"
echo -e "  Env file : ${ENV_FILE}"
echo ""
echo -e "  ${YELLOW}Useful commands:${RESET}"
echo "  sudo systemctl status novaops          # check service"
echo "  sudo journalctl -u novaops -f          # live logs"
echo "  sudo -u $APP_USER bash -c 'cd $APP_DIR && source .venv/bin/activate && export \$(cat .env | xargs) && python manage.py <cmd>'"
echo ""
