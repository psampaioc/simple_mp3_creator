.PHONY: install dev test lint

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r backend/requirements.lock
	cd frontend && npm ci

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals."

backend:
	PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

test:
	PYTHONPATH=backend pytest -q
	cd frontend && npm test

lint:
	PYTHONPATH=backend ruff check backend
	cd frontend && npm run lint

