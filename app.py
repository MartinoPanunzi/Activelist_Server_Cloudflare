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
from flask_sqlalchemy import SQLAlchemy

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
# Legacy JSON (migrato automaticamente a SQLite se presente)
LEGACY_DB_FILE = os.path.join(BASE_DIR, 'users_db.json')
EMAIL_COUNTER_FILE = os.path.join(BASE_DIR, "email_counter.json")
# Nuovo DB SQLite (portfolio-ready)
INSTANCE_FOLDER = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_FOLDER, exist_ok=True)
SQLITE_PATH = os.path.join(INSTANCE_FOLDER, 'activelist.db')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['QR_FOLDER'] = QR_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024  # 6MB max upload
# SQLAlchemy - SQLite file-based, perfetto per Raspberry/portfolio, zero config
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{SQLITE_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Modello DB ---
class User(db.Model):
    __tablename__ = 'users'
    token = db.Column(db.String(64), primary_key=True)  # uuid hex
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    img_filename = db.Column(db.String(255), nullable=False)
    qr_filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "name": self.name,
            "email": self.email,
            "img_filename": self.img_filename,
            "qr_filename": self.qr_filename,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

# Crea tabelle + migrazione automatica da JSON legacy
with app.app_context():
    db.create_all()
    # Se DB vuoto ma esiste users_db.json legacy, importa
    try:
        if db.session.query(User).count() == 0 and os.path.exists(LEGACY_DB_FILE):
            with open(LEGACY_DB_FILE, "r", encoding="utf-8") as f:
                legacy = json.load(f) or {}
            imported = 0
            for tok, data in legacy.items():
                if not tok or not isinstance(data, dict):
                    continue
                email = (data.get("email") or "").strip().lower()
                if not email or User.query.filter_by(email=email).first():
                    continue
                if User.query.get(tok):
                    continue
                u = User(
                    token=tok,
                    name=data.get("name", "Senza nome"),
                    email=email,
                    img_filename=data.get("img_filename", ""),
                    qr_filename=data.get("qr_filename", ""),
                )
                db.session.add(u)
                imported += 1
            if imported:
                db.session.commit()
                logging.info(f"Migrazione automatica: importati {imported} utenti da users_db.json -> SQLite")
            else:
                logging.info("DB SQLite vuoto, nessun dato legacy da migrare (o già migrato)")
    except Exception as e:
        logging.error(f"Errore migrazione legacy JSON -> SQLite: {e}")
        logging.error(traceback.format_exc())

# --- Config SMTP ---
secrets = {}
# Prova prima il path relativo (portabile per portfolio/localhost), poi fallback al vecchio path Raspberry
possible_paths = [
    os.path.join(BASE_DIR, "configuration_file.json"),
    "/home/mike/Desktop/server_activelist/Activelist/configuration_file.json",
]
config_path = next((p for p in possible_paths if os.path.exists(p)), None)

if config_path:
    try:
        with open(config_path, "r", encoding="utf-8") as cfg:
            secrets = json.load(cfg)
            logging.info(f"Configurazione caricata da {config_path}")
    except Exception as e:
        logging.error("Errore caricamento configuration_file.json: %s", e)
        logging.error(traceback.format_exc())
else:
    logging.warning("configuration_file.json non trovato; cerco variabili d'ambiente / uso default localhost")


app.config['BASE_URL'] = secrets.get("BASE_URL") or os.environ.get("BASE_URL") or "http://127.0.0.1:5000"
app.config['SMTP_SERVER'] = secrets.get("SMTP_SERVER") or os.environ.get("SMTP_SERVER") or 'smtp.gmail.com'
app.config['SMTP_PORT'] = int(secrets.get("SMTP_PORT") or os.environ.get("SMTP_PORT") or 587)
app.config['SMTP_USER'] = secrets.get("SMTP_USER") or os.environ.get("SMTP_USER")
app.config['SMTP_PASS'] = secrets.get("SMTP_PASS") or os.environ.get("SMTP_PASS")
app.config['SEND_EMAIL'] = bool(app.config['SMTP_USER'] and app.config['SMTP_PASS'])
if not app.config['SEND_EMAIL']:
    logging.warning("SMTP non configurato -> modalita' portfolio: le registrazioni funzioneranno senza invio email (ideale per screenshot locali)")

# --- Costanti limite email ---
EMAIL_LIMIT = 480
EMAIL_WINDOW_HOURS = 24

# --- Helpers ---
def make_token():
    return uuid.uuid4().hex

def compress_and_save_image(file_storage, out_path, max_size=(800, 800), quality=75):
    """
    Salva l'immagine compressa sempre in verticale.
    - max_size: dimensione massima (width, height)
    - quality: qualità JPEG
    """
    try:
        img = Image.open(file_storage.stream).convert('RGB')

        # Corregge orientamento basato su EXIF
        img = ImageOps.exif_transpose(img)

        # Forza sempre verticale (altezza >= larghezza)
        width, height = img.size
        if width > height:
            img = img.rotate(90, expand=True)

        # Ridimensiona mantenendo proporzioni
        img.thumbnail(max_size)

        # Salva immagine compressa
        img.save(out_path, format='JPEG', quality=quality, optimize=True)

        logging.info("Immagine compressa e salvata in verticale in %s", out_path)

    except Exception as e:
        logging.error("Errore compress_and_save_image: %s", e, exc_info=True)
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

        # --- Controllo email duplicata via SQLite (atomic, no race) ---
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error="Questa email è già registrata!")

        # --- Preparazione file ---
        token = make_token()
        # evita collisione token (praticamente impossibile, ma sicuro)
        while User.query.get(token):
            token = make_token()

        safe_name = secure_filename(photo.filename)
        img_filename = f"{token}_{safe_name.rsplit('.',1)[0]}.jpg"
        out_path = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)

        verify_url = f"{app.config['BASE_URL']}/verify?id={token}"
        qr_filename = f"{token}.png"
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)

        # --- Genera QR ---
        generate_qr(verify_url, qr_path)

        subject = "Il tuo QR code di verifica"
        body = f"Ciao {name},\n\nEcco il link per la verifica: {verify_url}\nIn allegato trovi il QR code."

        if app.config['SEND_EMAIL']:
            result = send_email_with_attachment(email, subject, body, qr_path)
        else:
            result = "OK"
            logging.info("Modalita' portfolio (SEND_EMAIL=False): salto invio email per %s, procedo con registrazione", email)

        # --- EMAIL OK ---
        if result == "OK":

            # Salva immagine compressa
            compress_and_save_image(photo, out_path)

            # Salva su SQLite
            new_user = User(token=token, name=name, email=email, img_filename=img_filename, qr_filename=qr_filename)
            db.session.add(new_user)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                # se violazione unique (race), torna errore duplicato
                if "UNIQUE constraint" in str(e) or "unique" in str(e).lower():
                    if os.path.exists(qr_path):
                        os.remove(qr_path)
                    if os.path.exists(out_path):
                        os.remove(out_path)
                    return render_template('register.html', error="Questa email è già registrata!")
                raise

            increment_email_counter()

            return render_template('success.html',
                                   token=token,
                                   qr_url=url_for('static', filename=f'qrcodes/{qr_filename}'))

        # --- Limite email superato ---
        elif result == "LIMIT_EXCEEDED":
            if os.path.exists(qr_path):
                os.remove(qr_path)
            return render_template('register.html', error="Limite invio email superato. Riprova più tardi.")

        # --- FALLIMENTO GENERICO ---
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
    user_obj = User.query.get(token) if token else None

    if user_obj:
        user = user_obj.to_dict()
        img_url = url_for("static", filename=f"uploads/{user_obj.img_filename}") if user_obj.img_filename else None
        return render_template("verify.html", ok=True, user=user, img_url=img_url)

    return render_template("verify.html", ok=False, token=token)



@app.route('/corsi')
def corsi():
    return render_template('corsi.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
