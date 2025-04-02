#!/bin/bash

# Couleurs pour les messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Démarrage de l'Assistant IA Local ===${NC}"

# Vérifier que Ollama est en cours d'exécution
if ! pgrep -x "ollama" > /dev/null; then
    echo -e "${YELLOW}Ollama n'est pas en cours d'exécution. Démarrage d'Ollama...${NC}"
    
    # Définir plus de threads pour Ollama pour améliorer les performances
    export OLLAMA_NUM_THREAD=4
    
    # Option 1: Démarrer Ollama comme un service en arrière-plan
    ollama serve &
    OLLAMA_PID=$!
    
    # Attendre que le service démarre
    echo -e "${YELLOW}Attente du démarrage d'Ollama...${NC}"
    sleep 5
    
    # Vérifier que Ollama est bien démarré
    if ! curl -s "http://localhost:11434/api/tags" > /dev/null; then
        echo -e "${RED}Erreur: Impossible de contacter Ollama sur le port 11434${NC}"
    else
        echo -e "${GREEN}Ollama démarré avec succès${NC}"
    fi
else
    echo -e "${GREEN}Ollama est déjà en cours d'exécution${NC}"
fi

# Vérifier les modèles disponibles
echo -e "${YELLOW}Vérification des modèles disponibles...${NC}"
MODELS=$(curl -s "http://localhost:11434/api/tags" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)

if [[ $MODELS == *"llama3"* ]]; then
    echo -e "${GREEN}Modèle llama3 trouvé${NC}"
else
    echo -e "${YELLOW}Le modèle llama3 n'est pas détecté. Voulez-vous le télécharger? (o/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([oO][uU][iI]|[oO])$ ]]; then
        echo -e "${YELLOW}Téléchargement du modèle llama3...${NC}"
        ollama pull llama3
    fi
fi

# Lancer l'application principale (qui intègre maintenant TTS et reconnaissance vocale)
echo -e "${GREEN}Démarrage de l'application principale...${NC}"

#python app.py
uvicorn app:app --host 0.0.0.0 --port 8000



# Capture des signaux pour fermer proprement
trap "echo -e '${YELLOW}Arrêt des services...${NC}'; if [ ! -z $OLLAMA_PID ]; then kill $OLLAMA_PID; fi; exit" INT TERM EXIT