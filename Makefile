.PHONY: up test lint format build

DC := docker compose
ROOT := --user 0:0

up:
	$(DC) up --build

build:
	$(DC) build

test:
	@echo "Aucun test automatisé n'est disponible."

lint:
	$(DC) run --rm $(ROOT) backend ruff check backend
	$(DC) run --rm $(ROOT) backend black --check backend

format:
	$(DC) run --rm $(ROOT) backend black backend
