#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/local-env.sh"
mkdir -p "$LHA_ROOT/.run" "$LHA_ROOT/data/minio"
DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then DOCKER=(sudo docker); fi
"${DOCKER[@]}" compose -f "$LHA_ROOT/deploy/docker-compose.yml" up -d --wait postgres redis milvus otel-collector
sudo systemctl link "$LHA_ROOT"/deploy/local/*.service
sudo systemctl daemon-reload
sudo systemctl start lha-local-minio
for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:9000/minio/health/live >/dev/null 2>&1; then break; fi
    sleep 1
done
curl -fsS http://127.0.0.1:9000/minio/health/live >/dev/null
"$LHA_ROOT/../.tools/uv-env/bin/python" "$LHA_ROOT/scripts/local/init-local-bucket.py"
cd "$LHA_ROOT/go-backend"
go run ./cmd/migrate up
go build -o "$LHA_ROOT/.run/lha-go" ./cmd/server
sudo systemctl start lha-local-python lha-local-go lha-local-web
for i in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && lsof -iTCP:50057 -sTCP:LISTEN >/dev/null 2>&1; then
        echo "服务已就绪：前端 http://localhost:5173；API http://localhost:8080/healthz"
        exit 0
    fi
    sleep 1
done
echo "服务未就绪，请检查 .run/*-systemd.log" >&2
exit 1
