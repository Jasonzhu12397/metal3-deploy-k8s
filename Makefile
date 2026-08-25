.PHONY: install up down logs migrate test lint fmt

install:
	./scripts/install.sh

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

test:
	cd backend && python -m pytest ../tests -v

lint:
	cd backend && python -m ruff check app

fmt:
	cd backend && python -m ruff format app
