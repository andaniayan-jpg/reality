#!/bin/sh
set -eu
escaped_base=$(printf '%s' "${REALITY_API_BASE:-}" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.REALITY_API_BASE = "%s";\n' "$escaped_base" > /usr/share/nginx/html/runtime-config.js
