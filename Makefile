.PHONY: install up down logs migrate test test-backend test-frontend lint fmt

install:
	./scripts/install.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest ../tests -v

test-frontend:
	cd frontend && npm test

lint:
	cd backend && python -m ruff check app

fmt:
	cd backend && python -m ruff format app
