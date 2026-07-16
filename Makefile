.PHONY: run test check docker-build up down logs

run:
	ARCHIVE_ADMIN_PASSWORD="$${DEV_ADMIN_PASSWORD:-development-only-password}" \
	ARCHIVE_DATA_DIR="$${DEV_DATA_DIR:-./.dev/data}" \
	ARCHIVE_ROOT="$${DEV_ARCHIVE_ROOT:-./.dev/archive}" \
	ARCHIVE_HOST=127.0.0.1 \
	ARCHIVE_PORT=8088 \
	python3 -m app

test:
	python3 -m unittest discover -s tests -v

check:
	python3 -m compileall -q app tests
	python3 -m unittest discover -s tests -v

docker-build:
	docker build -t overdrive-archive:local .

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f archive
