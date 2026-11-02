.PHONY: env up down reset logs lint format test test-catalog test-booking typecheck typecheck-catalog typecheck-booking superuser

env:
	python scripts/init_env.py

up: env
	docker compose up -d --build

down:
	docker compose down

reset:
	docker compose down --volumes

logs:
	docker compose logs -f --tail=100

lint:
	uvx ruff@0.17.3 check .
	uvx ruff@0.17.3 format --check .

format:
	uvx ruff@0.17.3 check --fix .
	uvx ruff@0.17.3 format .

test: test-catalog test-booking

test-catalog:
	cd services/catalog && uv run --frozen pytest

test-booking:
	cd services/booking && uv run --frozen pytest

typecheck: typecheck-catalog typecheck-booking

typecheck-catalog:
	cd services/catalog && uv run --frozen mypy .

typecheck-booking:
	cd services/booking && uv run --frozen mypy .

superuser:
	docker compose exec catalog-api python manage.py createsuperuser
