Voici le contenu **complet du `README.md`** à jour :

---

```markdown
# 🧠 Nova - Assistant vocal local intelligent

Nova est un assistant vocal 100% local, rapide, intelligent, et respectueux de ta vie privée.  
Il utilise Whisper.cpp pour la reconnaissance vocale, Piper pour la synthèse vocale, Ollama pour le LLM (ex: LLaMA 3), et une mémoire hybride sémantique + synthétique.

---

## 🚀 Stack technique

| Fonction | Stack utilisée | Détail |
|----------|----------------|--------|
| **Reconnaissance vocale** (STT) | `webrtcvad` + `whisper.cpp` | Silencieux détecté automatiquement |
| **Synthèse vocale** (TTS) | `Piper` (streaming PCM) | Lecture fluide et locale |
| **LLM** | `Ollama` + modèle (ex: `llama3`) | Génération de réponse |
| **Mémoire sémantique** | `SentenceTransformer` + `FAISS` | Embedding de phrases et recherche des souvenirs proches |
| **Mémoire synthétique** | Résumés organisés par thème | Compression automatique des connaissances |
| **Orchestration** | FastAPI + HTML/JS | UI simple, rapide, accessible sur `localhost` |


✅ Un moteur LLM local (Ollama) en streaming
✅ Une mémoire sémantique vectorielle bien foutue (FAISS + ID)
✅ Une mémoire synthétique compressée pour les résumés
✅ Une UI admin efficace
✅ TTS Piper + STT Whisper (local et performant)
✅ Un design modulaire

---

## 🧠 Mécanisme de mémoire

### 1. Mémoire vectorielle (SemanticMemory)

- Transforme chaque message utilisateur en vecteur (`MiniLM`)
- Stocke les vecteurs dans une base FAISS (`faiss.index`)
- Associe chaque vecteur à un `mapping.json` contenant `user + assistant`
- Lors d’une nouvelle question, cherche les 3 souvenirs les plus proches

### 2. Mémoire synthétique (SyntheticMemory)

- Crée des résumés thématiques compressés, datés, notés par importance
- Ex :  
  ```json
  {
    "theme": "data security",
    "summary": "L'utilisateur protège ses backups via chiffrage GPG.",
    "importance": 8,
    "timestamp": "2025-03-30T16:42:15Z"
  }
  ```
- Compression automatique si la mémoire devient trop grosse ou trop vieille

### 3. Fusion dans le prompt

À chaque appel LLM, le prompt est reconstruit ainsi :
```
[SYSTEM] Tu es Nova, un assistant vocal
[Résumé synthétique 1]
[Résumé synthétique 2]
[Souvenir sémantique 1]
[Souvenir sémantique 2]
[Historique de la session]
[USER] Ma question
```

---

## 📂 Arborescence

```
Nova/
│
├── app.py                       # Lanceur principal FastAPI
├── run.sh                       # Script de démarrage
├── TTS/
│   ├── voice_module.py          # Enregistrement + VAD
│   ├── tts_module.py            # Lecture vocale PCM
│   └── chat_engine.py           # Orchestration LLM + mémoire
├── CoreIA/
│   ├── semantic_memory.py       # Mémoire vectorielle FAISS
│   ├── synthetic_memory.py      # Résumés synthétiques
│   └── personality.json         # Prompt système
├── static/
│   ├── index.html               # UI HTML
│   ├── script.js                # JS frontend
│   └── styles.css               # Styles
└── memory/
    ├── history/                 # Vecteurs FAISS + mapping.json
    └── summary/                 # Résumés synthétiques
```

---

## 🔧 Configuration

- ⚠️ `whisper.cpp` doit être compilé avec l’exécutable `whisper-cli` accessible dans `opt/whisper.cpp/build/`
- 🧠 LLM (`llama3`, `mistral`, ...) géré via Ollama, vérifie avec :
  ```bash
  ollama list
  ```

---

## 🛠️ Améliorations futures

| Idée | Bénéfice |
|------|----------|
| Compression dynamique basée sur la latence | Plus rapide quand la mémoire grossit |
| Auto-thématisation des résumés | Groupes de connaissance plus clairs |
| Interface de gestion mémoire | Supprimer ou revoir les souvenirs |
| Historique complet archivé | Navigation chronologique ou par thème |
| Feedback explicatif | L’IA peut justifier "pourquoi elle se souvient" |


---

## 🛡️ Respect de la vie privée

Aucun appel réseau externe, tout est local.  
Pas de tracking, pas d’API externe, pas de dépendance cloud.  
Nova tourne **chez toi**, pour **toi**, en toute sécurité.