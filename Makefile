.PHONY: up down logs shell demo reset build

# Start NovaOPS (builds if needed)
up:
	@[ -f .env ] || cp .env.example .env
	docker compose up --build -d
	@echo ""
	@echo "  NovaOPS is starting…"
	@echo "  URL   : http://localhost:$$(grep '^PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8000)"
	@echo "  Admin : $$(grep '^ADMIN_EMAIL=' .env 2>/dev/null | cut -d= -f2 || echo admin@novaops.local)"
	@echo "  Pass  : $$(grep '^ADMIN_PASSWORD=' .env 2>/dev/null | cut -d= -f2 || echo novaops123)"
	@echo ""

# Stop NovaOPS
down:
	docker compose down

# Live logs
logs:
	docker compose logs -f

# Django management shell
shell:
	docker compose exec web python manage.py shell

# Reload demo data (WARNING: wipes existing data)
demo:
	docker compose exec web python manage.py create_demo_data

# Full reset — removes all data volumes and rebuilds
reset:
	docker compose down -v
	docker compose up --build -d

# Build image without starting
build:
	docker compose build
