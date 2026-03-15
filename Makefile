.PHONY: run install migrate docker-up docker-down test

install:
	pip install -r requirements.txt

run:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Миграции через Alembic
migrate-init:
	alembic init alembic

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

migrate-up:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

# Docker
docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f app

# Tests
test:
	pytest tests/ -v

# Dev helpers
shell:
	python -c "from core.database import SessionLocal; db = SessionLocal(); print('DB ready')"
