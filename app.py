# -*- coding: utf-8 -*-
import os
import uuid
import threading
import logging
import traceback
import json
import time
from datetime import datetime
from PIL import Image, ImageOps

from flask import Flask, request, render_template, url_for

try:
    from werkzeug.utils import secure_filename
except Exception as e:
    raise ImportError("werkzeug mancante: installa 'werkzeug' o aggiorna Flask") from e

try:
    from PIL import Image, ExifTags
except Exception as e:
    raise ImportError("Pillow non installato. Esegui: pip install pillow") from e

try:
    import qrcode
except Exception as e:
    raise ImportError("qrcode non installato. Esegui: pip install qrcode") from e

import smtplib
from email.message import EmailMessage

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Config principali ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
QR_FOLDER = os.path.join(BASE_DIR, 'static', 'qrcodes')
DB_FILE = os.path.join(BASE_DIR, 'users_db.json')
EMAIL_COUNTER_FILE = os.path.join(BASE_DIR, "email_counter.json")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['QR_FOLDER'] = QR_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024  # 6MB max upload

# --- Config SMTP ---
secrets = {}
config_path = "/home/mike/Desktop/server_activelist/Activelist/configuration_file.json"

if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as cfg:
            secrets = json.load(cfg)
            logging.info("Configurazione caricata da configuration_file.json")
    except Exception as e:
        logging.error("Errore caricamento configuration_file.json: %s", e)
        logging.error(traceback.format_exc())
else:
    logging.warning(f"configuration_file.json non trovato in {config_path}; cerco variabili d'ambiente")


app.config['BASE_URL'] = secrets.get("BASE_URL") or os.environ.get("BASE_URL") or "http://localhost:5000"
app.config['SMTP_SERVER'] = 'smtp.gmail.com'
app.config['SMTP_PORT'] = 587
app.config['SMTP_USER'] = secrets.get("SMTP_USER") or os.environ.get("SMTP_USER")
app.config['SMTP_PASS'] = secrets.get("SMTP_PASS") or os.environ.get("SMTP_PASS")
app.config['SEND_EMAIL'] = bool(app.config['SMTP_USER'] and app.config['SMTP_PASS'])

# --- Costanti limite email ---
EMAIL_LIMIT = 480
EMAIL_WINDOW_HOURS = 36

# --- Carica DB utenti ---
users_db = {}
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            users_db = json.load(f) or {}
            logging.info("Database utenti caricato.")
    except Exception as e:
        logging.error("Errore aprendo users_db.json: %s", e)
        users_db = {}

# --- Helpers ---
def make_token():
    return uuid.uuid4().hex

def compress_and_save_image(file_storage, out_path, max_size=(800,800), quality=75):
    try:
        img = Image.open(file_storage.stream).convert('RGB')
        img = ImageOps.exif_transpose(img)  # corregge orientamento EXIF
        img = img.rotate(-90, expand=True)
        img.thumbnail(max_size)
        img.save(out_path, format='JPEG', quality=quality, optimize=True)
        logging.info("Immagine compressa salvata in %s", out_path)
    except Exception as e:
        logging.error("Errore compress_and_save_image: %s", e)
        logging.error(traceback.format_exc())
        raise


def generate_qr(data, out_path):
    try:
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(out_path)
        logging.info("QR generato in %s", out_path)
    except Exception as e:
        logging.error("Errore generate_qr: %s", e)
        logging.error(traceback.format_exc())
        raise

def send_email_with_attachment(to_address, subject, body, attachment_path=None):
    if not app.config['SEND_EMAIL']:
        logging.warning("SMTP non configurato: salto invio email.")
        return False

    msg = EmailMessage()
    msg['From'] = f"ActiveList Server <{app.config['SMTP_USER']}>"
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.set_content(body)

    if attachment_path:
        try:
            abs_path = os.path.abspath(attachment_path)
            with open(abs_path, 'rb') as f:
                data = f.read()
                ext = abs_path.split('.')[-1].lower()
                subtype = 'jpeg' if ext in ('jpg', 'jpeg') else 'png'
                msg.add_attachment(data, maintype='image', subtype=subtype, filename=os.path.basename(abs_path))
        except Exception as e:
            logging.error("Errore apertura allegato: %s", e)
            return False

    try:
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as smtp:
            smtp.starttls()
            smtp.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
            smtp.send_message(msg)
        return "OK"

    except Exception as e:
        logging.error("Errore invio email: %s", e)
        if "Daily user sending limit exceeded" in str(e) or "rate limit" in str(e).lower():
            return "LIMIT_EXCEEDED"
        return False


# --- Limite email ---
def load_email_counter():
    if os.path.exists(EMAIL_COUNTER_FILE):
        try:
            with open(EMAIL_COUNTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("timestamps", [])
        except:
            return []
    return []

def save_email_counter(timestamps):
    with open(EMAIL_COUNTER_FILE, "w", encoding="utf-8") as f:
        json.dump({"timestamps": timestamps}, f)

def check_email_limit():
    now = time.time()
    timestamps = load_email_counter()
    cutoff = now - EMAIL_WINDOW_HOURS * 3600
    timestamps = [t for t in timestamps if t > cutoff]
    save_email_counter(timestamps)
    return len(timestamps) < EMAIL_LIMIT

def increment_email_counter():
    timestamps = load_email_counter()
    timestamps.append(time.time())
    save_email_counter(timestamps)

# --- Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/Infocollab')
def Infocollab():
    return render_template('Infocollab.html')

@app.route('/register', methods=['GET', 'POST'])
def register():

    # --- BLOCCO se limite superato ---
    if not check_email_limit():
        return render_template('register.html',
                               error="Il nostro server ha ricevuto troppe richieste. Riprovare tra 24 ore."), 429

    if request.method == 'GET':
        return render_template('register.html')

    try:
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        photo = request.files.get('photo')

        if not name or not email or not photo or photo.filename == '':
            return render_template('register.html', error="Compila tutti i campi!")

        if not email.endswith("@liceotorelli.edu.it"):
            return render_template('register.html', error="Usa un indirizzo @liceotorelli.edu.it")

        if any(u.get('email','').lower() == email for u in users_db.values()):
            return render_template('register.html', error="Questa email è già registrata!")

        # --- Preparazione file ---
        token = make_token()
        safe_name = secure_filename(photo.filename)
        img_filename = f"{token}_{safe_name.rsplit('.',1)[0]}.jpg"
        out_path = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)

        verify_url = url_for('verify', id=token, _external=True)
        qr_filename = f"{token}.png"
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)

        # --- Genera QR prima dell’email ---
        generate_qr(verify_url, qr_path)

        subject = "Il tuo QR code di verifica"
        body = f"Ciao {name},\n\nEcco il link per la verifica: {verify_url}\nIn allegato trovi il QR code."

        result = send_email_with_attachment(email, subject, body, qr_path) if app.config['SEND_EMAIL'] else False

        # --- Email inviata con successo ---
        if result == "OK":
            compress_and_save_image(photo, out_path)

            users_db[token] = {
                "name": name,
                "email": email,
                "img_filename": img_filename,
                "qr_filename": qr_filename
            }

            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(users_db, f, indent=4, ensure_ascii=False)

            increment_email_counter()

            return render_template('success.html',
                                   token=token,
                                   qr_url=url_for('static', filename=f'qrcodes/{qr_filename}'))

        # --- Limite superato ---
        elif result == "LIMIT_EXCEEDED":
            if os.path.exists(qr_path):
                os.remove(qr_path)
            return render_template('register.html', error="Limite invio email superato. Riprova più tardi.")

        # --- Email fallita generica ---
        else:
            if os.path.exists(qr_path):
                os.remove(qr_path)
            if os.path.exists(out_path):
                os.remove(out_path)
            return render_template('register.html', error="Errore invio email. Riprova più tardi.")

    except Exception as e:
        logging.error("Errore in /register: %s", e)
        logging.error(traceback.format_exc())
        return render_template('register.html',
                               error="Si è verificato un errore. Contatta l'assistenza."), 500


@app.route('/verify')
def verify():
    token = request.args.get('id')
    user = users_db.get(token)
    if user:
        img_url = url_for('static', filename=f'uploads/{user.get('img_filename')}') if user.get('img_filename') else None
        return render_template('verify.html', ok=True, user=user, img_url=img_url)
    return render_template('verify.html', ok=False, token=token)


@app.route('/corsi')
def corsi():
    return render_template('corsi.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

