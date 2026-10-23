#!/usr/bin/env bash
# CI'ın koştuğu kontrollerin yereldeki karşılığı (ADR-0014 md.10).
# Kullanım:  bash scripts/kontrol.sh
# Veritabanı testleri DATABASE_URL varsa koşar, yoksa sebebiyle atlanır.
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$KOK/api/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$KOK/api/.venv/bin/python"

echo "── API ────────────────────────────────────────────"
cd "$KOK/api"
"$PY" -m ruff format --check .
"$PY" -m ruff check .
"$PY" -m mypy
"$PY" -m pytest -q

echo "── Sözleşme ───────────────────────────────────────"
"$PY" - <<'PYEOF'
import json
from talimatname.api.app import create_app
from talimatname.settings import Settings
with open("../spec/openapi.json", "w", encoding="utf-8") as f:
    json.dump(create_app(Settings(database_url=None)).openapi(), f, ensure_ascii=False, indent=2)
PYEOF
cd "$KOK"
git diff --exit-code spec/openapi.json >/dev/null || {
  echo "spec/openapi.json güncel değil — commit edin"; exit 1; }

echo "── Panel ──────────────────────────────────────────"
cd "$KOK/web"
npx prettier --check src
npm run -s lint
npx tsc -b
npm test -- --run
npm run -s api:tipler
cd "$KOK"
git diff --exit-code web/src/api/schema.ts >/dev/null || {
  echo "web/src/api/schema.ts güncel değil — commit edin"; exit 1; }

echo "── Hepsi geçti ────────────────────────────────────"
