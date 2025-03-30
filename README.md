# Assistant IA Local

Un assistant IA conversationnel local avec interface web futuriste et reconnaissance vocale.

## Description

Ce projet implémente un assistant IA entièrement local utilisant Ollama comme backend pour les modèles de langage, avec une interface web réactive et une reconnaissance vocale basée sur whisper.cpp. L'assistant répond à vos questions en mode texte ou vocal, avec une visualisation dynamique de son état.

## Fonctionnalités

- 💬 Chat avec interface web réactive
- 🎤 Reconnaissance vocale basée sur whisper.cpp
- 🎭 Visualisation dynamique de l'état de l'IA avec animations
- 🔄 Sélection et utilisation de différents modèles LLM (via Ollama)
- 🎯 Optimisé pour la rapidité et la réactivité

## Prérequis

- Python 3.8+
- [Ollama](https://github.com/ollama/ollama) installé et configuré
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) compilé localement

## Installation

1. Clonez ce dépôt :
```bash
git clone https://github.com/votre-nom/assistant-ia-local.git
cd assistant-ia-local
```

2. Créez un environnement virtuel et installez les dépendances :
```bash
python -m venv venv
source venv/bin/activate  # Sur macOS/Linux
pip install -r requirements.txt
```

3. Assurez-vous d'avoir whisper.cpp compilé :
```bash
# Si vous n'avez pas encore whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp.git opt/whisper.cpp
cd opt/whisper.cpp
make
# Téléchargez un modèle (base ou medium recommandé)
bash ./models/download-ggml-model.sh base
cd ../..
```

4. Assurez-vous d'avoir au moins un modèle téléchargé dans Ollama :
```bash
ollama pull llama3
```

## Utilisation

1. Lancez le script de démarrage :
```bash
./run.sh
```

2. Accédez à l'interface web à l'adresse : http://localhost:8000

3. Commencez à discuter avec l'assistant :
   - Tapez votre message et appuyez sur Entrée
   - Ou cliquez sur l'icône du microphone pour parler

## Structure du projet

- `app.py`: Application principale FastAPI
- `voice_service.py`: Service Flask pour la reconnaissance vocale
- `static/`: Répertoire contenant les fichiers frontend
  - `index.html`: Structure de l'interface
  - `styles.css`: Styles et animations
  - `script.js`: Logique frontend
- `run.sh`: Script de démarrage des services

## Configuration

- Les chemins vers whisper.cpp peuvent être configurés dans `voice_service.py`
- Les paramètres de reconnaissance vocale sont ajustables dans `voice_service.py`
- L'URL de l'API Ollama peut être configurée dans `app.py`

## Résolution des problèmes

- **Port occupé**: Si le port 5000 ou 5001 est déjà utilisé, modifiez-le dans `voice_service.py` et `script.js`
- **Erreurs GPU**: Si vous rencontrez des erreurs GPU avec whisper.cpp, assurez-vous que l'option `--no-gpu` est activée dans `voice_service.py`
- **Problèmes de transcription**: Essayez d'utiliser un modèle plus petit (tiny ou base) pour améliorer la vitesse

## Améliorations futures

- Ajout d'une base de connaissances personnelle
- Connecteurs pour services domotiques
- Synthèse vocale pour les réponses
- Accès et analyse de fichiers locaux
- Migration vers un système dédié (Raspberry Pi/NUC)

## Licence

MIT

---

## requirements.txt

```
fastapi==0.103.1
uvicorn==0.23.2
flask==2.3.3
flask-cors==4.0.0
sounddevice==0.4.6
numpy==1.24.4
wave==0.0.2
python-dotenv==1.0.0
pydantic==2.4.2
requests==2.31.0
```