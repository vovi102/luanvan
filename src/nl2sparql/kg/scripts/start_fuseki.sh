#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd -P)"
COMPOSE_FILE="${PROJECT_ROOT}/infrastructure/docker/docker-compose.fuseki.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run Fuseki for this project." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required to run Fuseki for this project." >&2
  exit 1
fi

echo "Starting Fuseki at http://localhost:3030/ with Docker Compose dataset /test"
exec docker compose -f "${COMPOSE_FILE}" up "$@"
