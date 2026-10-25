BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: install install-backend install-frontend migrate test test-backend test-frontend lint lint-backend lint-frontend format format-backend dev dev-backend dev-frontend

install: install-backend install-frontend

install-backend:
	cd $(BACKEND_DIR) && python3 -m pip install -e '.[dev]'

install-frontend:
	cd $(FRONTEND_DIR) && npm install

migrate:
	cd $(BACKEND_DIR) && alembic upgrade head

test: test-backend test-frontend

test-backend:
	cd $(BACKEND_DIR) && pytest

test-frontend:
	cd $(FRONTEND_DIR) && npm test

lint: lint-backend lint-frontend

lint-backend:
	cd $(BACKEND_DIR) && ruff format --check . && ruff check .

lint-frontend:
	cd $(FRONTEND_DIR) && npm run lint

format: format-backend
	cd $(FRONTEND_DIR) && npm run format

format-backend:
	cd $(BACKEND_DIR) && ruff format . && ruff check --fix .

dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd $(BACKEND_DIR) && mkdir -p .agentflow && AGENTFLOW_DB_PATH=.agentflow/agentflow.db alembic upgrade head && AGENTFLOW_DB_PATH=.agentflow/agentflow.db uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev
