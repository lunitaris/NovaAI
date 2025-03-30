#!/bin/bash

# Vérifier que Ollama est en cours d'exécution
if ! pgrep -x "ollama" > /dev/null; then
    echo "Ollama n'est pas en cours d'exécution. Démarrage d'Ollama..."
    # Option 1: Démarrer Ollama comme un service en arrière-plan
    ollama serve &
    # Attendre que le service démarre
    sleep 5
fi

# Lancer le service de reconnaissance vocale en arrière-plan
echo "Démarrage du service de reconnaissance vocale..."
python voice_service.py &
VOICE_PID=$!

# Lancer l'application principale
echo "Démarrage de l'application principale..."
python app.py

# Capture des signaux pour fermer proprement
trap "kill $VOICE_PID; exit" INT TERM EXIT