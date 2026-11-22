#!/usr/bin/env bash
# Operates on the current host only. Does not create AWS infrastructure.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -f .env ]]; then
  echo 'Copy .env.example to .env and configure it first.' >&2
  exit 1
fi
compose=(docker compose --env-file .env -f compose.yaml)

case "${1:-}" in
  validate)
    "${compose[@]}" config --quiet
    ;;
  deploy)
    if grep -Eq 'REPLACE_WITH_TESTED_VERSION|OWNER/REPOSITORY|FULL_COMMIT_SHA' .env; then
      echo 'Replace the example image references with tested versions first.' >&2
      exit 1
    fi
    "${compose[@]}" config --quiet
    chmod 600 .env
    # The published app image runs as UID/GID 1000. Preserve existing data.
    sudo install -d -o 1000 -g 1000 data/financial_data data/logs
    "${compose[@]}" pull
    "${compose[@]}" up -d --wait --wait-timeout 180
    curl --fail --silent --show-error http://127.0.0.1:8766/api/research > /dev/null
    echo 'UI startup check passed. Model inference has not been tested.'
    ;;
  models)
    # Match the models in the published image's configs/settings.yaml.
    "${compose[@]}" exec -T ollama ollama pull qwen3:8b
    "${compose[@]}" exec -T ollama ollama pull bge-m3:latest
    ;;
  status)
    "${compose[@]}" ps
    ;;
  stop)
    "${compose[@]}" stop
    echo 'Containers stopped. AWS instance and disk billing are NOT stopped.'
    ;;
  *)
    echo 'Usage: bash deploy.sh {validate|deploy|models|status|stop}' >&2
    exit 2
    ;;
esac
