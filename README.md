# ActiveList — Sistema di Verifica Studenti con QR Code

> Web app Flask deployata su **Raspberry Pi** per gestire la verifica degli studenti e l'accesso a 12+ convenzioni locali a Fano. Progetto reale usato da 40+ studenti del Liceo Torelli.

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-black)
![Raspberry Pi](https://img.shields.io/badge/Deploy-Raspberry%20Pi-C51A4A)
![License](https://img.shields.io/badge/License-MIT-green)

**Live demo locale:** `http://127.0.0.1:5000` · **Stack:** Python, Flask, Pillow, qrcode, Gunicorn/Nginx

---

## Il Problema

La lista studentesca **Active List** aveva accordi con 12 attività locali (bar, ristoranti, negozi) che offrivano sconti agli studenti. Il controllo avveniva a voce o con liste cartacee: lento, falsificabile, ingestibile per i negozianti.

Serveva un sistema **economico (budget zero), offline-friendly e senza app da installare** che permettesse al negoziante di verificare in 2 secondi che lo sconto fosse richiesto da uno studente reale.

## La Soluzione

Flusso end-to-end in 4 step:

1.  **Registrazione** (`/register`): studente inserisce nome + email istituzionale `@liceotorelli.edu.it` + selfie (obbligatorio). Validazione sia lato client che server.
2.  **Elaborazione**: 
    - Correzione orientamento EXIF + forzatura verticale + compressione JPEG (Pillow, `thumbnail 800x800, quality 75`)
    - Generazione `UUID` come token univoco (RFC 4122)
    - Generazione QR Code contenente `BASE_URL/verify?id=TOKEN` (qrcode 7.0)
3.  **Invio**: Email automatica con QR in allegato via SMTP Gmail + allegato PNG/JPEG. Rate limiting 480 email / 24h con `email_counter.json`.
4.  **Verifica in cassa** (`/verify?id=TOKEN`): il negoziante scansiona il QR, vede foto + nome + email. Nessun login richiesto, pagina leggera e veloce anche su 4G.

Tutto gira su un **Raspberry Pi** con Gunicorn + socket Unix, costo hardware < 50€.

## Demo

### Avvio rapido (portfolio / localhost)

```bash
# 1. Clona e entra nella cartella
git clone <repo> && cd Activelist

# 2. Crea venv e installa dipendenze
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
# source venv/bin/activate
pip install -r requirements.txt

# 3. Configura (modalità portfolio senza email)
cp configuration_file.example.json configuration_file.json
# Modifica BASE_URL se vuoi: http://127.0.0.1:5000 di default

# 4. Inizializza DB + demo (solo prima volta, o dopo git clone)
python scripts/seed_demo.py        # crea instance/activelist.db + 3 utenti demo + QR/avatar
# oppure se hai un vecchio users_db.json: python scripts/migrate_json_to_sqlite.py

# 5. Avvia
python app.py          # dev
# oppure: ./start.sh       # dev (Flask) | ./start.sh prod  (Gunicorn)
# -> http://127.0.0.1:5000
# -> http://127.0.0.1:5000/register
# -> http://127.0.0.1:5000/verify?id=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2
```

**Utenti demo già pronti** (dopo `python seed_demo.py`):
- `a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2` — Mario Rossi
- `b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2c3d4` — Giulia Bianchi
- `c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2c3d4e5` — Luca Verdi

Prova: `http://127.0.0.1:5000/verify?id=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2`

### Screenshots (consigliati per portfolio)

| Home | Registrazione | Success + QR | Verifica |
|------|---------------|--------------|----------|
| `templates/index.html` | `templates/register.html` | `templates/success.html` | `templates/verify.html` |

> Suggerimento: fai screen sia desktop (1920x1080) che mobile (390x844) con DevTools.

## Stack Tecnico

| Layer | Tecnologia | Perché |
|-------|------------|--------|
| Backend | **Flask 3.1** | Leggero, ideale per Raspberry Pi |
| Image processing | **Pillow 12.x** | `exif_transpose`, `thumbnail`, compressione JPEG |
| QR | **qrcode 8.2** | Generazione server-side, nessun servizio esterno |
| DB | **SQLite + SQLAlchemy** (`instance/activelist.db`) | File-based come prima ma ACID, unique constraint su email, migrazione automatica da legacy `users_db.json` |
| Email | `smtplib` + Gmail SMTP | Allegato automatico, gestione `LIMIT_EXCEEDED` |
| Deploy | **Gunicorn + Nginx** su Raspberry Pi OS | `gunicorn.sock`, `wsgi.py` |

## Architettura

```
[ Browser ] -> [ Nginx :80 ] -> [ Gunicorn (wsgi:app) ] -> [ Flask app.py + SQLAlchemy ]
                                          |
                    +---------------------+---------------------+
                    |                     |                     |
              static/uploads/      static/qrcodes/      instance/activelist.db
              (foto compresse)     (QR PNG)              (SQLite: users)
```

**Punti tecnici interessanti:**
- Gestione EXIF: le foto da smartphone arrivano ruotate, `ImageOps.exif_transpose` + forzatura verticale evita foto storte in verifica.
- **SQLite vs JSON**: prima JSON aveva race condition con Gunicorn (rilettura file). Ora `UNIQUE(email)` a livello DB + `db.session.commit()` atomico, zero race. Migrazione automatica al primo avvio se trova `users_db.json` legacy.
- Rate limiting email persistito su file per sopravvivere ai restart.
- Modello `User(token PK, email UNIQUE, name, img/qr, created_at)` — pronto per estensioni (scadenza QR, admin panel).

## Struttura Progetto

```
Activelist/
├── app.py                      # App Flask + SQLAlchemy (modello User)
├── wsgi.py                     # Entry point Gunicorn
├── start.sh                    # Avvio dev/prod (venv + Flask/Gunicorn)
├── requirements.txt
├── .editorconfig, .gitattributes, .gitignore
├── .github/workflows/ci.yml    # CI: pip install + pytest
├── configuration_file.json     # Config (BASE_URL, SMTP) - ignorato da git
├── configuration_file.example.json
├── instance/                   # SQLite (ignorato, creato al primo avvio)
│   └── activelist.db
├── scripts/
│   ├── migrate_json_to_sqlite.py
│   └── seed_demo.py            # Seed 3 utenti demo per portfolio
├── docs/
│   ├── case-study.md           # Testi portfolio pronti da copiare
│   └── screenshots/README.md   # Guida screenshot
├── tests/
│   └── test_app.py             # 5 test con test_client (spiegabili)
├── static/
│   ├── style.css, styleinfocollab.css, corsi.css
│   ├── gallery/, media/
│   ├── uploads/                # Foto (ignorato, 3 demo whitelistati)
│   └── qrcodes/                # QR (ignorato, 3 demo whitelistati)
└── templates/
    ├── index.html, Infocollab.html, corsi.html
    ├── register.html, success.html, verify.html
```

## Configurazione

`configuration_file.json`:
```json
{
  "BASE_URL": "http://127.0.0.1:5000",
  "SMTP_USER": "",
  "SMTP_PASS": ""
}
```

- Se `SMTP_USER/PASS` vuoti → **modalità portfolio**: la registrazione funziona senza inviare email (log `modalità portfolio`), perfetto per demo/screenshot.
- Se configurati → invio reale via `smtp.gmail.com:587`. Richiede App Password Gmail.

Variabili d'ambiente alternative: `BASE_URL`, `SMTP_USER`, `SMTP_PASS`, `SMTP_SERVER`, `SMTP_PORT` (hanno priorità se `configuration_file.json` non trovato).

## Test

```bash
pip install -r requirements.txt
pytest -v
# 5 passed in 0.6s
```

Test in `tests/test_app.py` — usano solo `app.test_client()` e `Pillow` per creare immagini fittizie. Nessun mock complicato, tutto spiegabile a colloquio.

## Cosa Migliorerei Oggi

> Trasparenza per il portfolio: il progetto funziona ma ha limiti voluti dal contesto (tempo/budget/Raspberry).

- [x] **DB**: migrato da JSON a SQLite + SQLAlchemy + script `migrate_json_to_sqlite.py` + `seed_demo.py` ✅
- [x] **Test**: 5 test pytest base (home, verify, duplicate email, register success) in `tests/test_app.py` ✅
- [ ] **Config**: usare `python-dotenv` invece di `configuration_file.json` + path hardcodato legacy (lasciato volutamente semplice)
- [ ] **Sicurezza**: hashing token, scadenza QR, validazione MIME più stretta
- [ ] **Docker**: `Dockerfile` + `docker-compose` (non aggiunto per mantenere semplicità spiegabile)
- [ ] **Frontend**: refactoring CSS (1440 righe in `style.css`, duplicazioni) + build step

Questi punti sono già in roadmap e mostrano consapevolezza dei trade-off, non errori.

## Deploy Originale (Raspberry Pi)

```bash
source bin/activate
export FLASK_APP=app
gunicorn --bind unix:gunicorn.sock wsgi:app --workers 3 --timeout 60
# Nginx proxy_pass -> unix:/home/mike/Desktop/server_activelist/Activelist/gunicorn.sock
```

## Licenza & Privacy

- Dati demo anonimizzati. I file reali `instance/activelist.db`, `users_db.json`, `static/uploads/*`, `static/qrcodes/*` sono in `.gitignore` e non committati (3 demo whitelistati).
- Backup reali salvati come `*.bak-real` solo in locale, mai pushati.
- Progetto nato per la lista **Active List - Liceo Torelli (Fano)**.
- **Migrazione**: se hai un vecchio deploy con `users_db.json`, basta avviare `python app.py` e viene migrato automaticamente; oppure `python scripts/migrate_json_to_sqlite.py --force` per re-import forzato.

---

**Autore:** [Il tuo nome] — Freelance Python/Flask Developer — [LinkedIn] · [Sito portfolio]

> *Cerchi un sistema simile per la tua associazione/attività? Contattami per un preventivo.*
