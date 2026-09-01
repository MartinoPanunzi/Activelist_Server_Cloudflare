# Testi pronti da incollare sul tuo portfolio freelance

---

### 1. Card / Griglia portfolio (titolo + sottotitolo 1 riga)

**ActiveList — Sistema verifica studenti con QR**
Web app Flask su Raspberry Pi per gestire 12 convenzioni locali e verificare l'identità studente in 2s via QR.

**Tag:** `Python` `Flask` `SQLite` `SQLAlchemy` `Raspberry Pi` `Pillow` `QR Code`
**Ruolo:** Full-stack, deploy, design leggero
**Anno:** 2025-2026 (refactor DB 2026)

---

### 2. Descrizione corta (per listing freelance Malt/Upwork/Fiverr)

Sistema reale per lista studentesca del Liceo Torelli (Fano): registrazione con email istituzionale + selfie, compressione immagine, generazione QR univoco, verifica in cassa per i negozianti. Deploy su Raspberry Pi con Gunicorn/Nginx, costo <50€. Flusso completo senza app da installare. Gestito picco di 40+ registrazioni.

---

### 3. Descrizione lunga (per pagina case study)

**Contesto**
La lista Active List aveva 12 attività convenzionate ma nessun modo affidabile per verificare gli aventi diritto allo sconto. Liste cartacee e passaparola non scalavano.

**Soluzione**
Ho progettato e deployato una web app end-to-end:
- Registrazione con validazione dominio `@liceotorelli.edu.it` e foto obbligatoria
- Elaborazione immagine: correzione EXIF, forzatura verticale, compressione 800x800
- Token UUID + QR Code con link di verifica
- Invio email automatico con rate limiting
- Pagina di verifica leggera per il negoziante (foto + nome)

**Vincoli**
Budget zero, hardware Raspberry Pi, nessun database esterno, tempo di consegna 2 settimane. Prima scelta JSON file-based per semplicità, poi migrato a SQLite + SQLAlchemy per ACID e scalabilità (migrazione automatica inclusa).

**Risultato**
Sistema usato attivamente, 12 convenzioni gestite, verifica in cassa <3s. Deploy stabile su Pi con Gunicorn socket.

**Stack**
Flask, SQLite + SQLAlchemy, Pillow, qrcode, smtplib, Gunicorn, Nginx, Raspberry Pi OS

**Cosa rifarei**
✅ DB già migrato a SQLite (2026) — restano Docker, test automatizzati, scadenza QR. Vedi README per roadmap.

---

### 4. Bullet per CV (1 riga)

Sviluppato sistema Flask + QR deployato su Raspberry Pi per verifica identità 40+ studenti e gestione 12 convenzioni locali — flusso registrazione/verifica end-to-end con elaborazione immagini e rate limiting email.

---

### 5. Testo per LinkedIn / Post

Ho trasformato un problema reale in 50€ di hardware:
una lista studentesca doveva verificare gli aventi diritto allo sconto in 12 negozi senza app.
Ho costruito con Flask un flusso registrazione (email istituzionale + selfie) → QR univoco → verifica in cassa in 2s, tutto su Raspberry Pi.
Niente SaaS, niente costi mensili. Solo Python, Pillow e un QR.
 Repo + demo locale nel README. #Flask #RaspberryPi #Python

---

### 6. FAQ per cliente che legge il portfolio

**Q: È scalabile?**
A: Sì, ora su SQLite con constraint UNIQUE e commit atomici. Per migliaia di utenti o multi-server, passo a Postgres in 1 giorno (stesso modello SQLAlchemy).

**Q: Si può adattare alla mia associazione?**
A: Sì, basta cambiare dominio email, logo e collaboratori. Il cuore (QR + verifica) è riusabile.

**Q: Quanto costa rifarlo?**
A: Base simile: 1-2 settimane. Con DB + Docker + pannello admin: 3 settimane.

---

### Come usarli
- Card -> griglia portfolio
- Descrizione lunga -> pagina /projects/activelist
- Bullet -> CV PDF
- Post LinkedIn -> quando pubblichi il repo
