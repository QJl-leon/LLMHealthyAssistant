#!/bin/bash
# source scripts/local/local-env.sh
LHA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="$LHA_ROOT/../.tools/go/bin:$LHA_ROOT/../.tools/node-v22.12.0-linux-x64/bin:$LHA_ROOT/../.tools/uv-env/bin:$LHA_ROOT/../.tools/bin:$PATH"
export UV_CACHE_DIR="$LHA_ROOT/../.tools/uv-cache"
