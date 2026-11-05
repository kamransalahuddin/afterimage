.PHONY: setup keys api web test samples

setup:
	cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m spacy download en_core_web_sm
	cd frontend && npm install

keys:
	@cd backend && .venv/bin/python -m app.cli genkey

api:
	cd backend && .venv/bin/uvicorn app.main:app_factory --factory --reload --port 8000 --no-access-log

web:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/python -m pytest -q

samples:
	cd backend && .venv/bin/python -m tests.fixtures.synthetic ../frontend/public/samples
