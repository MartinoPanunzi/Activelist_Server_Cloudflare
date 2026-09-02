#!/bin/bash
# ActiveList - avvio locale / Raspberry Pi
# Uso:
#   chmod +x start.sh
#   ./start.sh              # sviluppo (Flask dev)
#   ./start.sh prod         # produzione (Gunicorn + SQLite)

set -e
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# attiva venv se presente (supporta sia venv/ che bin/ legacy)
if [ -f "$BASE_DIR/venv/bin/activate" ]; then
  source "$BASE_DIR/venv/bin/activate"
elif [ -f "$BASE_DIR/bin/activate" ]; then
  source "$BASE_DIR/bin/activate"
fi

export FLASK_APP=app
if [ "$1" = "prod" ]; then
  export FLASK_ENV=production
  echo "[prod] avvio Gunicorn su SQLite $BASE_DIR/instance/activelist.db"
  # crea DB se manca + seed demo se vuoto
  python -c "from app import app, db; app.app_context().push(); db.create_all()" 2>&1 | head -n 20
  exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 60 wsgi:app
else
  export FLASK_ENV=development
  echo "[dev] http://127.0.0.1:5000  (SQLite portfolio mode se SMTP vuoto)"
  exec flask run --host=0.0.0.0 --port=5000
fi
