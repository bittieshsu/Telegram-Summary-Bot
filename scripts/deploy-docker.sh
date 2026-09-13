#!/usr/bin/env bash
set -euo pipefail

: "${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"

for command in docker flock install mktemp; do
  command -v "$command" >/dev/null
done
docker compose version >/dev/null

deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
base_compose="$deploy_dir/docker-compose.yml"
production_compose="$deploy_dir/docker-compose.production.yml"

[[ -f "$base_compose" ]]
[[ -f "$production_compose" ]]

ghcr_token="$(cat)"
[[ -n "$ghcr_token" ]]

docker_config="$(mktemp -d)"
base_snapshot="$(mktemp "$deploy_dir/.docker-compose.base.XXXXXX")"
production_snapshot="$(mktemp "$deploy_dir/.docker-compose.production.XXXXXX")"
cleanup() {
  rm -rf -- "$docker_config"
  rm -f -- "$base_snapshot" "$production_snapshot"
}
trap cleanup EXIT
chmod 700 "$docker_config"

exec 9>"$deploy_dir/.deploy.lock"
flock -w 600 9

install -m 600 "$base_compose" "$base_snapshot"
install -m 600 "$production_compose" "$production_snapshot"

export DOCKER_CONFIG="$docker_config"
export IMAGE_REPOSITORY IMAGE_TAG
printf '%s' "$ghcr_token" | docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin
unset ghcr_token

docker compose \
  --project-directory "$deploy_dir" \
  -f "$base_snapshot" \
  -f "$production_snapshot" pull
docker compose \
  --project-directory "$deploy_dir" \
  -f "$base_snapshot" \
  -f "$production_snapshot" up -d --no-build --remove-orphans
