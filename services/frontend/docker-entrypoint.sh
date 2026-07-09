#!/bin/sh
set -e

API_BASE="${API_BASE_URL:-http://localhost:5000}"
sed -i "s|%%API_BASE%%|${API_BASE}|g" /usr/share/nginx/html/index.html

exec nginx -g "daemon off;"
