# =============================================================================
# Configuration
# =============================================================================
PYTHON := python
PIP := pip
SERVER_PORT := 8000
SERVER_CMD := $(PYTHON) -m uvicorn flo.server.app:app --host 0.0.0.0 --port $(SERVER_PORT) --reload

# =============================================================================
# Directory Setup
# =============================================================================
$(shell mkdir -p .pids .logs)

# =============================================================================
# Default Target
# =============================================================================
.DEFAULT_GOAL := help

help:
	@echo "Available targets:"
	@echo ""
	@echo "  Setup:"
	@echo "    make install          Install all dependencies"
	@echo "    make install-dev      Install with dev dependencies"
	@echo ""
	@echo "  Quality:"
	@echo "    make lint             Run ruff linter"
	@echo "    make format           Auto-format code with ruff"
	@echo "    make typecheck        Run mypy type checker"
	@echo "    make validate         Run lint + typecheck"
	@echo ""
	@echo "  Testing:"
	@echo "    make test             Run all tests"
	@echo "    make test-cov         Run tests with coverage"
	@echo ""
	@echo "  Server:"
	@echo "    make run              Start the server (background)"
	@echo "    make stop             Stop the server"
	@echo "    make restart          Restart the server"
	@echo "    make status           Show service status"
	@echo "    make logs             Show recent logs"
	@echo "    make logs-follow      Follow logs in real-time"
	@echo ""
	@echo "  Utility:"
	@echo "    make clean            Remove build artifacts"

# =============================================================================
# Setup
# =============================================================================
install:
	@echo "📦 Installing dependencies..."
	@$(PIP) install -e .
	@echo "✅ Dependencies installed"

install-dev:
	@echo "📦 Installing dev dependencies..."
	@$(PIP) install -e ".[dev,google]"
	@echo "✅ Dev dependencies installed"

# =============================================================================
# Quality
# =============================================================================
lint:
	@echo "🔍 Running ruff..."
	@$(PYTHON) -m ruff check src/ tests/
	@$(PYTHON) -m ruff format --check src/ tests/
	@echo "✅ Lint passed"

format:
	@echo "🎨 Formatting code..."
	@$(PYTHON) -m ruff check --fix src/ tests/
	@$(PYTHON) -m ruff format src/ tests/
	@echo "✅ Formatted"

typecheck:
	@echo "🔎 Running mypy..."
	@$(PYTHON) -m mypy src/
	@echo "✅ Type check passed"

validate: lint typecheck

# =============================================================================
# Testing
# =============================================================================
test:
	@echo "🧪 Running tests..."
	@$(PYTHON) -m pytest

test-cov:
	@echo "🧪 Running tests with coverage..."
	@$(PYTHON) -m pytest --cov=flo --cov-report=term-missing

# =============================================================================
# Server Lifecycle
# =============================================================================
run:
	@if lsof -ti:$(SERVER_PORT) > /dev/null 2>&1; then \
		echo "❌ Server already running on port $(SERVER_PORT)"; \
		exit 1; \
	fi
	@echo "🚀 Starting server on port $(SERVER_PORT)..."
	@nohup $(SERVER_CMD) > .logs/server.log 2>&1 & echo $$! > .pids/server.pid
	@echo "✅ Server started (PID: $$(cat .pids/server.pid))"

stop:
	@if [ -f .pids/server.pid ]; then \
		PID=$$(cat .pids/server.pid); \
		if ps -p $$PID > /dev/null 2>&1; then \
			echo "🛑 Stopping server (PID: $$PID)..."; \
			kill -TERM -- -$$PID 2>/dev/null || kill $$PID; \
			rm .pids/server.pid; \
			echo "✅ Server stopped"; \
		else \
			echo "⚠️  Server process not found, cleaning up PID file"; \
			rm .pids/server.pid; \
		fi \
	else \
		echo "ℹ️  Server not running"; \
	fi

restart: stop run

status:
	@echo "📊 Service Status:"
	@echo ""
	@if [ -f .pids/server.pid ]; then \
		PID=$$(cat .pids/server.pid); \
		if ps -p $$PID > /dev/null 2>&1; then \
			echo "  ✅ server: running (PID: $$PID)"; \
		else \
			echo "  ❌ server: stopped (stale PID file)"; \
		fi \
	else \
		echo "  ⚪ server: not running"; \
	fi

logs:
	@if [ -f .logs/server.log ]; then \
		tail -n 50 .logs/server.log; \
	else \
		echo "No logs found"; \
	fi

logs-follow:
	@tail -f .logs/server.log 2>/dev/null

# =============================================================================
# Utility
# =============================================================================
clean:
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean"

.PHONY: help install install-dev lint format typecheck validate test test-cov run stop restart status logs logs-follow clean
