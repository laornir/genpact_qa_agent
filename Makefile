.PHONY: run-db run test lint format

run-db:
	docker compose up -d db
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec db pg_isready -U $${POSTGRES_USER:-university} -d $${POSTGRES_DB:-university} > /dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "Postgres is ready."

run: run-db
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

test:
	DB_DRIVER=sqlite pytest tests/ -v --cov=. --cov-report=term-missing

format:
	ruff format .
	ruff check --fix .

lint:
	ruff check .
	mypy .
