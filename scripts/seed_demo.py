#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed 3 utenti demo anonimizzati per portfolio/screenshot
Uso: python seed_demo.py [--reset]
Crea anche le immagini placeholder e i QR se mancanti.
"""
import os, argparse
from PIL import Image, ImageDraw, ImageFont
import qrcode

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, BASE_DIR)
from app import app, db, User

DEMO = [
    ("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2", "Mario Rossi", "mario.rossi@liceotorelli.edu.it"),
    ("b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2c3d4", "Giulia Bianchi", "giulia.bianchi@liceotorelli.edu.it"),
    ("c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2c3d4e5", "Luca Verdi", "luca.verdi@liceotorelli.edu.it"),
]

def make_avatar(name, out_path):
    img = Image.new('RGB', (600, 800), color=(13,27,143))
    draw = ImageDraw.Draw(img)
    draw.ellipse([150,100,450,400], fill=(255,221,0))
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()
    draw.text((300,500), name, fill="white", anchor="mm", font=font)
    draw.text((300,560), "DEMO", fill=(255,221,0), anchor="mm", font=font)
    img.save(out_path, "JPEG", quality=85)
    print(f"avatar {out_path}")

def make_qr(token, out_path):
    url = f"http://127.0.0.1:5000/verify?id={token}"
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white")
    qimg.save(out_path)
    print(f"qr {out_path}")

def seed(reset=False):
    with app.app_context():
        db.create_all()
        if reset:
            for tok,_,_ in DEMO:
                u = User.query.get(tok)
                if u:
                    db.session.delete(u)
            db.session.commit()
            print("reset demo esistenti")

        for tok, name, email in DEMO:
            if User.query.get(tok) or User.query.filter_by(email=email).first():
                print(f"skip {email} già presente")
                continue
            img_filename = f"{tok}_demo.jpg"
            qr_filename = f"{tok}.png"
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
            qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
            if not os.path.exists(img_path):
                make_avatar(name, img_path)
            if not os.path.exists(qr_path):
                make_qr(tok, qr_path)
            u = User(token=tok, name=name, email=email, img_filename=img_filename, qr_filename=qr_filename)
            db.session.add(u)
            print(f"seed {name} ({email}) -> {tok[:8]}...")
        db.session.commit()
        print(f"seed completato, totale utenti: {User.query.count()}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    seed(reset=args.reset)
