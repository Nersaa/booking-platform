.PHONY: env up down reset logs seed loadtest-up loadtest lint format test test-catalog test-booking test-payment-mock typecheck typecheck-catalog typecheck-booking typecheck-payment-mock superuser

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

seed:
	python loadtest/seed.py --count 300

# Load test mode: abuse limits lifted, see docs/load-testing.md.
LOADTEST = docker compose -f docker-compose.yml -f loadtest/docker-compose.yml

loadtest-up: env
	$(LOADTEST) up -d --build

loadtest:
	$(LOADTEST) run --rm locust

lint:
	uvx ruff@0.17.3 check .
	uvx ruff@0.17.3 format --check .

format:
	uvx ruff@0.17.3 check --fix .
	uvx ruff@0.17.3 format .

test: test-catalog test-booking test-payment-mock

test-catalog:
	cd services/catalog && uv run --frozen pytest

test-booking:
	cd services/booking && uv run --frozen pytest

test-payment-mock:
	cd services/payment-mock && uv run --frozen pytest

typecheck: typecheck-catalog typecheck-booking typecheck-payment-mock

typecheck-catalog:
	cd services/catalog && uv run --frozen mypy .

typecheck-booking:
	cd services/booking && uv run --frozen mypy .

typecheck-payment-mock:
	cd services/payment-mock && uv run --frozen mypy .

superuser:
	docker compose exec catalog-api python manage.py createsuperuser
