"""
Test semplici per ActiveList — cose che puoi spiegare a colloquio.
- test_home: verifica che la home risponda 200
- test_verify_demo: verifica che un token demo esista e mostri il nome
- test_register_duplicate_email: prova a registrare email già presente -> errore
- test_register_success: registrazione nuova (modalità portfolio senza invio email) -> success + DB
Tutti usano Flask test_client, niente mock complicati.
"""
import os
from io import BytesIO
from PIL import Image

from app import app, db, User


def _make_dummy_image():
    """Crea un'immagine JPEG 100x100 in memoria, come se fosse upload."""
    img = Image.new("RGB", (100, 100), color="blue")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_home():
    with app.test_client() as c:
        resp = c.get("/")
        assert resp.status_code == 200
        assert b"Active List" in resp.data


def test_verify_demo():
    # token demo creato da seed_demo.py
    tok = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a1b2"
    with app.test_client() as c:
        resp = c.get(f"/verify?id={tok}")
        assert resp.status_code == 200
        assert b"Mario Rossi" in resp.data
        assert b"mario.rossi" in resp.data


def test_verify_invalid():
    with app.test_client() as c:
        resp = c.get("/verify?id=notexist123")
        assert resp.status_code == 200
        assert b"Token non valido" in resp.data


def test_register_duplicate_email():
    buf = _make_dummy_image()
    with app.test_client() as c:
        resp = c.post(
            "/register",
            data={
                "name": "Test Dup",
                "email": "mario.rossi@liceotorelli.edu.it",  # già presente
                "photo": (buf, "test.jpg"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        # messaggio di errore dell'app
        assert "già registrata".encode() in resp.data


def test_register_success_and_verify():
    buf = _make_dummy_image()
    email = "test.pytest@liceotorelli.edu.it"
    # cleanup se test precedente non ha pulito
    with app.app_context():
        old = User.query.filter_by(email=email).first()
        if old:
            try:
                os.remove(os.path.join(app.config["UPLOAD_FOLDER"], old.img_filename))
            except: pass
            try:
                os.remove(os.path.join(app.config["QR_FOLDER"], old.qr_filename))
            except: pass
            db.session.delete(old)
            db.session.commit()

    with app.test_client() as c:
        resp = c.post(
            "/register",
            data={
                "name": "Test Pytest",
                "email": email,
                "photo": (buf, "test2.jpg"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Registrazione completata" in resp.data

        # verifica che sia in DB e verificabile
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            assert u is not None
            assert u.name == "Test Pytest"
            tok = u.token

        resp2 = c.get(f"/verify?id={tok}")
        assert b"Test Pytest" in resp2.data

        # cleanup finale
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            if u:
                try:
                    os.remove(os.path.join(app.config["UPLOAD_FOLDER"], u.img_filename))
                except: pass
                try:
                    os.remove(os.path.join(app.config["QR_FOLDER"], u.qr_filename))
                except: pass
                db.session.delete(u)
                db.session.commit()

    with app.app_context():
        assert User.query.filter_by(email=email).first() is None
