# 🧠 Nova - Assistant Vocal IA Local

Nova est un assistant vocal intelligent totalement local, axé sur le respect de la vie privée et l'autonomie complète. Cette application permet aux utilisateurs de communiquer naturellement via la voix ou en mode texte tout en exploitant une gestion avancée de la mémoire.

## ⚙️ Stack Technique

### Reconnaissance Vocale (STT)
- **Whisper.cpp** : Permet de convertir la voix en texte efficacement, même sur des appareils peu puissants.

### Synthèse Vocale (TTS)
- **Piper TTS** : Moteur de synthèse vocale léger et performant utilisé pour générer la réponse audio en temps réel (mode PCM streaming).

### Modèle de Langage (LLM)
- **Ollama** : Permet l'exécution locale de modèles de langage tels que `llama3`, fournissant des réponses rapides et cohérentes en mode streaming.

### Infrastructure Web
- **FastAPI** : Backend web moderne et performant assurant la gestion des requêtes API.
- **Uvicorn** : Serveur ASGI pour déployer l'application FastAPI.

### Interface Utilisateur
- **HTML/CSS/JavaScript** : Interface web intuitive pour administrer Nova et gérer la mémoire via une page d'administration complète.

### Gestion de la Mémoire
Nova utilise trois types de mémoires pour fournir une expérience utilisateur fluide et pertinente :

#### 1. Mémoire Volatile (Short Term)
- Stockage temporaire des interactions récentes pour un contexte immédiat.
- Fichier : `volatile_memory.py`

#### 2. Mémoire Sémantique
- Basée sur FAISS (vectorielle).
- Permet de retrouver des souvenirs similaires en fonction du contexte de la conversation.
- Fichier : `semantic_memory.py`

#### 3. Mémoire Synthétique
- Stocke des résumés thématiques condensés à partir des interactions.
- Utilisée pour maintenir un contexte à long terme sans surcharger la mémoire.
- Comprend une gestion automatisée de la purge basée sur l'importance et le temps écoulé.
- Fichier : `synthetic_memory.py`

### Moteur de Résumés
- **Summary Engine** : Génère automatiquement des résumés pour alimenter la mémoire synthétique à partir des interactions utilisateur-assistant.
- Fichier : `summary_engine.py`

### Modules de Support
- **Chat Engine** : Prépare la conversation en intégrant la mémoire sémantique, synthétique et volatile pour fournir un contexte optimal au modèle.
- **Memory Manager** : Gère la coordination et l'accès aux différentes mémoires du système.

## 🚀 Fonctionnement Général
Lors d'une interaction utilisateur :

1. Whisper.cpp transcrit la voix en texte.
2. Le texte est envoyé au Chat Engine, qui intègre les mémoires pour générer une réponse contextualisée via Ollama.
3. La réponse textuelle est transformée en audio en streaming par Piper TTS.
4. L'interaction est stockée dans les mémoires sémantique et synthétique pour enrichir les interactions futures.

## 🎛️ Page d'Administration
Nova inclut une interface web complète permettant :
- La gestion des résumés synthétiques (consultation, modification, suppression).
- L'exploration et la gestion de la mémoire sémantique (recherche vectorielle, visualisation des derniers souvenirs).
- La visualisation des statistiques et thèmes dominants dans la mémoire synthétique.

## 📈 Idées d'Amélioration
- **Optimisation de Performance** : Amélioration des performances de recherche vectorielle avec des index optimisés.
- **Personnalisation** : Interface permettant à l'utilisateur de modifier la personnalité et les comportements de Nova directement depuis l'interface d'administration.
- **Automatisation Avancée** : Intégration de workflows avancés pour automatiser certaines tâches via n8n etc..
