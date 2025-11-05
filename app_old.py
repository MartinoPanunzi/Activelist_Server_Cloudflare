# -*- coding: utf-8 -*-
import os
import uuid
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
import qrcode
import smtplib
from email.message import EmailMessage
import json

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
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024  # max 6MB upload

app.config['BASE_URL'] = 'http://192.168.1.100:5000'
app.config['SMTP_SERVER'] = 'smtp.gmail.com'
app.config['SMTP_PORT'] = 587
app.config['SMTP_USER'] = 'activelistserver@gmail.com'
app.config['SMTP_PASS'] = 'ieyu hulv jkfa gopl'
app.config['SEND_EMAIL'] = True

# --- Carica database JSON ---
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r") as f:
            users_db = json.load(f)
    except json.JSONDecodeError:
        users_db = {}
else:
    users_db = {}

# --- Helpers ---
def make_token():
    return uuid.uuid4().hex

def compress_and_save_image(file_storage, out_path, max_size=(800,800), quality=75):
    img = Image.open(file_storage.stream)
    img = img.convert('RGB')
    # Ruota in base ai dati EXIF
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = img._getexif()
        if exif is not None:
            orientation_value = exif.get(orientation, None)
            if orientation_value == 3:
                img = img.rotate(180, expand=True)
            elif orientation_value == 6:
                img = img.rotate(270, expand=True)
            elif orientation_value == 8:
                img = img.rotate(90, expand=True)
        else:
            img = img.rotate(90, expand=True)  # default se non ci sono dati EXIF
    except Exception:
        img = img.rotate(90, expand=True)
    img.thumbnail(max_size)
    img.save(out_path, format='JPEG', quality=quality, optimize=True)

def generate_qr(data, out_path):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(out_path)

def send_email_with_attachment(to_address, subject, body, attachment_path=None):
    if not app.config['SMTP_SERVER']:
        print("SMTP non configurato, salto invio email.")
        return False
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = app.config['SMTP_USER']
    msg['To'] = to_address
    msg.set_content(body)
    if attachment_path:
        with open(attachment_path, 'rb') as f:
            data = f.read()
            subtype = os.path.splitext(attachment_path)[1].lstrip('.').lower()
            if subtype == 'jpg':
                subtype = 'jpeg'
            msg.add_attachment(data, maintype='image', subtype=subtype, filename=os.path.basename(attachment_path))
    try:
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as smtp:
            smtp.starttls()
            smtp.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
            smtp.send_message(msg)
        print(f"Email inviata a {to_address}")
        return True
    except Exception as e:
        print(f"Errore invio email: {e}")
        return False

# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('register'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    name = request.form.get('name')
    email = request.form.get('email')
    photo = request.files.get('photo')

    if not name or not email or not photo or photo.filename == '':
        return render_template('register.html', error="Non siamo cosi' stupidi -_-")

    if not email.lower().endswith("@liceotorelli.edu.it"):
        return render_template('register.html', error="Non siamo cosi' stupidi -_-")

    # Controllo email unica
    for user in users_db.values():
        if user['email'].lower() == email.lower():
            return render_template('register.html', error="Questa email e' gia' registrata!")

    token = make_token()

    # salva immagine
    safe_name = secure_filename(photo.filename)
    img_filename = f"{token}_{safe_name.rsplit('.',1)[0]}.jpg"
    out_path = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
    compress_and_save_image(photo, out_path)

    # genera QR
    base = app.config['BASE_URL'].rstrip('/')
    verify_url = f"{base}{url_for('verify')}?id={token}"
    qr_filename = f"{token}.png"
    qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
    generate_qr(verify_url, qr_path)

    # salva su DB
    users_db[token] = {
        "name": name,
        "email": email,
        "img_filename": img_filename,
        "qr_filename": qr_filename
    }
    with open(DB_FILE, "w") as f:
        json.dump(users_db, f, indent=4)

    # invia email
    if app.config['SEND_EMAIL']:
        subject = "Il tuo QR code di verifica"
        body = f"Ciao {name},\n\nEcco il link per la verifica: {verify_url}\nIn allegato trovi il QR code."
        send_email_with_attachment(email, subject, body, qr_path)

    return render_template('success.html', token=token, qr_url=url_for('static', filename=f'qrcodes/{qr_filename}'))

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

