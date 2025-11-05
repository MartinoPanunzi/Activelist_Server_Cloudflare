import qrcode
import os

def generate_qr(data, filename=None):
    # Crea cartella static/qrcodes se non esiste
    qr_folder = os.path.join(os.getcwd(), "static", "qrcodes")
    os.makedirs(qr_folder, exist_ok=True)

    # Se non viene passato un filename, usa l'ID come nome file
    if not filename:
        filename = f"{data}.png"

    path = os.path.join(qr_folder, filename)

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=5
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill="black", back_color="white")
    img.save(path)

    # Ritorna percorso relativo per poterlo usare in HTML
    return f"qrcodes/{filename}"
