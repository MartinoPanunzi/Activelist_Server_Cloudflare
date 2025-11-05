# -*- coding: utf-8 -*-
import os
import uuid
import threading
import logging
import traceback
import json

from flask import Flask, request, render_template, redirect, url_for

# try imports that may be missing
try:
    from werkzeug.utils import secure_filename
except Exception as e:
    raise ImportError("werkzeug mancante: installa 'werkzeug' o assicurati che Flask sia aggiornato") from e

# PIL / qrcode possono non essere installati
try:
    from PIL import Image, ExifTags
except Exception as e:
    raise ImportError("Pillow (PIL) non installato. Esegui: pip install pillow") from e

try:
    import qrcode
except Exception as e:
    raise ImportError("qrcode non installato. Esegui: pip install qrcode") from e

import smtplib
from email.message import EmailMessage

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Config ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
QR_FOLDER = os.path.join(BASE_DIR, 'static', 'qrcodes')
DB_FILE = os.path.join(BASE_DIR, 'users_db.json')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['QR_FOLDER'] = QR_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024  # 6MB

# Load configuration_file.json safely
secrets = {}
config_path = os.path.join(BASE_DIR, "configuration_file.json")
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as cfg:
            secrets = json.load(cfg)
            logging.info("Configurazione caricata da configuration_file.json")
    except Exception as e:
        logging.error("Errore caricamento configuration_file.json: %s", e)
        logging.error(traceback.format_exc())
else:
    logging.warning("configuration_file.json non trovato; cerco variabili d'ambiente")

# Fallback a env vars se manca qualche chiave
app.config['BASE_URL'] = secrets.get("BASE_URL") or os.environ.get("BASE_URL") or "http://localhost:5000"
app.config['SMTP_SERVER'] = 'smtp.gmail.com'
app.config['SMTP_PORT'] = 587
app.config['SMTP_USER'] = secrets.get("SMTP_USER") or os.environ.get("SMTP_USER")
app.config['SMTP_PASS'] = secrets.get("SMTP_PASS") or os.environ.get("SMTP_PASS")
app.config['SEND_EMAIL'] = bool(app.config['SMTP_USER'] and app.config['SMTP_PASS'])

# --- Carica DB JSON in modo robusto ---
users_db = {}
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            users_db = json.load(f) or {}
            logging.info("Database utenti caricato.")
    except json.JSONDecodeError:
        logging.error("users_db.json corrotto: inizializzo DB vuoto.")
        users_db = {}
    except Exception as e:
        logging.error("Errore aprendo users_db.json: %s", e)
        users_db = {}
else:
    users_db = {}

# --- Helpers ---
def make_token():
    return uuid.uuid4().hex

def compress_and_save_image(file_storage, out_path, max_size=(800,800), quality=75):
    try:
        img = Image.open(file_storage.stream)
        img = img.convert('RGB')
        # EXIF handling: cerca Orientation se esiste, altrimenti non ruotare
        try:
            exif = img._getexif()
            if exif is not None:
                orientation_key = None
                for k, v in ExifTags.TAGS.items():
                    if v == 'Orientation':
                        orientation_key = k
                        break
                if orientation_key:
                    orientation_value = exif.get(orientation_key, None)
                    if orientation_value == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation_value == 6:
                        img = img.rotate(270, expand=True)
                    elif orientation_value == 8:
                        img = img.rotate(90, expand=True)
        except Exception:
            logging.debug("EXIF non disponibile o errore EXIF; salto rotazione.", exc_info=True)

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
    if not app.config.get('SMTP_USER') or not app.config.get('SMTP_PASS'):
        logging.warning("SMTP non configurato: salto invio email.")
        return False

    msg = EmailMessage()
    msg['From'] = f"ActiveList Server <{app.config['SMTP_USER']}>"
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.set_content(body)

    if attachment_path:
        try:
            with open(attachment_path, 'rb') as f:
                data = f.read()
                ext = attachment_path.split('.')[-1].lower()
                subtype = 'jpeg' if ext in ('jpg','jpeg') else ext
                msg.add_attachment(data, maintype='image', subtype=subtype, filename=os.path.basename(attachment_path))
        except Exception as e:
            logging.error("Errore apertura allegato: %s", e)
            logging.error(traceback.format_exc())

    try:
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as smtp:
            smtp.starttls()
            smtp.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
            smtp.send_message(msg)
        logging.info("Email inviata a %s", to_address)
        return True
    except Exception as e:
        logging.error("Errore invio email: %s", e)
        logging.error(traceback.format_exc())
        return False

def send_email_async(to, subject, body, attachment=None):
    thread = threading.Thread(target=send_email_with_attachment, args=(to, subject, body, attachment))
    thread.daemon = True
    thread.start()

# --- Routes ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/Infocollab')
def Infocollab():
    return render_template('Infocollab.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
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

        for user in users_db.values():
            if user.get('email', '').strip().lower() == email:
                return render_template('register.html', error="Questa email è già registrata!")

        token = make_token()
        safe_name = secure_filename(photo.filename)
        img_filename = f"{token}_{safe_name.rsplit('.',1)[0]}.jpg"
        out_path = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
        compress_and_save_image(photo, out_path)

        base = app.config['BASE_URL'].rstrip('/')
        verify_url = f"{base}{url_for('verify')}?id={token}"
        qr_filename = f"{token}.png"
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        generate_qr(verify_url, qr_path)

        users_db[token] = {
            "name": name,
            "email": email,
            "img_filename": img_filename,
            "qr_filename": qr_filename
        }
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(users_db, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error("Errore scrittura DB: %s", e)
            logging.error(traceback.format_exc())

        if app.config.get('SEND_EMAIL'):
            subject = "Il tuo QR code di verifica"
            body = f"Ciao {name},\n\nEcco il link per la verifica: {verify_url}\nIn allegato trovi il QR code."
            send_email_async(email, subject, body, qr_path)

        return render_template(
            'success.html',
            token=token,
            qr_url=url_for('static', filename=f'qrcodes/{qr_filename}')
        )
    except Exception as e:
        logging.error("Errore in /register: %s", e)
        logging.error(traceback.format_exc())
        # mostra una pagina di errore amichevole in produzione o dettagliata in debug
        return render_template('register.html', error="Si è verificato un errore durante la registrazione. Controlla i log."), 500

@app.route('/verify')
def verify():
    token = request.args.get('id')
    if not token:
        return "ID mancante", 400

    user = users_db.get(token)
    if user:
        img_filename = user.get("img_filename")
        img_url = url_for('static', filename=f'uploads/{img_filename}') if img_filename else None
        return render_template('verify.html', ok=True, user=user, img_url=img_url)
    else:
        return render_template('verify.html', ok=False, token=token)

@app.route('/corsi')
def corsi():
    return render_template('corsi.html')

if __name__ == '__main__':
    # ATTENZIONE: in produzione togli debug=True
    app.run(host='0.0.0.0', port=5000, debug=True)



