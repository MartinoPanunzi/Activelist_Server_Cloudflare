import smtplib
from email.message import EmailMessage
import os

def send_email_local(to_address, subject, body, attachment_path=None):
    msg = EmailMessage()
    msg['From'] = "ActiveList Server <activelistserver@raspberrypi.local>"
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.set_content(body)

    if attachment_path:
        with open(attachment_path, 'rb') as f:
            msg.add_attachment(f.read(), maintype='image', subtype='png', filename='qrcode.png')

    try:
        with smtplib.SMTP('localhost') as smtp:
            smtp.send_message(msg)
        print(f"? Email inviata a {to_address}")
        return True
    except Exception as e:
        print(f"? Errore invio email: {e}")
        return False
