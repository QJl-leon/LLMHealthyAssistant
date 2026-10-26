#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/local-env.sh"
sudo systemctl stop lha-local-web lha-local-go lha-local-python
if [[ "${1:-}" == "--all" ]]; then
    sudo systemctl stop lha-local-minio
    DOCKER=(docker)
    if ! docker info >/dev/null 2>&1; then DOCKER=(sudo docker); fi
    "${DOCKER[@]}" compose -f "$LHA_ROOT/deploy/docker-compose.yml" stop
fi
