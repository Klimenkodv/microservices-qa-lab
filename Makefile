.PHONY: up down clean test test-backend test-frontend test-integration

up:
	docker compose up --build

down:
	docker compose down

clean:
	docker compose down -v
	rm -f data/*.db data/*.db-shm data/*.db-wal

test: test-backend test-frontend

test-backend:
	docker build -f services/auth-service/Dockerfile.test -t qa-lab-auth-tests .
	docker run --rm qa-lab-auth-tests
	docker build -f services/notification-service/Dockerfile.test -t qa-lab-notification-tests .
	docker run --rm qa-lab-notification-tests
	docker build -f services/statistics-service/Dockerfile.test -t qa-lab-statistics-tests .
	docker run --rm qa-lab-statistics-tests

test-frontend:
	docker run --rm -v "$(CURDIR)/frontend:/app" -w /app node:22.11.0-alpine sh -c "npm ci --no-audit --no-fund && npm test"

test-integration:
	RUN_INTEGRATION=1 python3 -m pytest tests/integration
