#!/bin/bash
set -e
local_ai_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$local_ai_root/local-ai" install "$@"
