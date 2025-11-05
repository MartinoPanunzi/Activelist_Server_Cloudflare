#!/bin/bash
# Attiva virtualenv
source /home/mike/Desktop/server_activelist/Activelist/bin/activate

# Imposta variabili Flask
export FLASK_APP=app
export FLASK_ENV=development  # o production

# Avvia il server Flask
flask run --host=0.0.0.0 --port=5000
