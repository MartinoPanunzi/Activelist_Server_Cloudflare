#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migra users_db.json -> instance/activelist.db (SQLite)
Uso: python migrate_json_to_sqlite.py [--force]
- Se --force, svuota la tabella prima di importare
- Mantiene idempotenza: salta email/token già esistenti
"""
import os, json, argparse, sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY = os.path.join(BASE_DIR, "users_db.json")

# importa app e db dopo aver settato path
sys.path.insert(0, BASE_DIR)
from app import app, db, User

def migrate(force=False):
    with app.app_context():
        db.create_all()
        if force:
            deleted = db.session.query(User).delete()
            db.session.commit()
            print(f"[FORCE] svuotati {deleted} record da SQLite")

        if not os.path.exists(LEGACY):
            print(f"Nessun {LEGACY} trovato, creo solo DB vuoto")
            print(f"DB pronto: {app.config['SQLALCHEMY_DATABASE_URI']} - utenti: {User.query.count()}")
            return

        with open(LEGACY, "r", encoding="utf-8") as f:
            legacy = json.load(f) or {}

        existing_emails = {u.email for u in User.query.all()}
        existing_tokens = {u.token for u in User.query.all()}
        imported = skipped = 0
        for tok, data in legacy.items():
            email = (data.get("email") or "").strip().lower()
            if not tok or not email:
                skipped += 1
                continue
            if tok in existing_tokens or email in existing_emails:
                skipped += 1
                continue
            u = User(token=tok, name=data.get("name","Senza nome"), email=email,
                     img_filename=data.get("img_filename",""), qr_filename=data.get("qr_filename",""))
            db.session.add(u)
            existing_tokens.add(tok)
            existing_emails.add(email)
            imported += 1
        db.session.commit()
        print(f"Migrazione completata: importati {imported}, saltati {skipped}, totale ora {User.query.count()}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="svuota SQLite prima di importare")
    args = p.parse_args()
    migrate(force=args.force)
