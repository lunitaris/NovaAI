from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import tempfile
import os
import subprocess
import numpy as np
import sounddevice as sd
import time
import io
import wave
import threading
import logging
import queue
import json
import sys
import importlib.util

# Vérifier si piper est installé
try:
    from piper import PiperVoice
    PIPER_INSTALLED = True
except ImportError:
    PIPER_INSTALLED = False
    print("Piper TTS n'est pas installé. Installation en cours...")
    subprocess.run([sys.executable, "-m", "pip", "install", "piper-tts"], check=True)
    from piper import PiperVoice

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tts_service.log")
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Activer CORS pour permettre les requêtes depuis notre interface

# Configuration de Piper TTS
MODELS_DIR = "tts_models"
VOICE_FILE = os.path.join(MODELS_DIR, "fr_FR-siwis-medium.onnx")
CONFIG_FILE = os.path.join(MODELS_DIR, "fr_FR-siwis-medium.json")

os.makedirs(MODELS_DIR, exist_ok=True)

# Variable globale pour stocker la voix piper
piper_voice = None
audio_queue = queue.Queue()
is_speaking = False
stop_speaking = False

def download_voice_model():
    """Télécharge le modèle de voix français si nécessaire"""
    if not os.path.exists(VOICE_FILE) or not os.path.exists(CONFIG_FILE):
        logger.info(f"Téléchargement du modèle de voix française...")
        
        # URL du modèle (à adapter selon le modèle souhaité)
        model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
        config_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.json"
        
        # Téléchargement des fichiers
        subprocess.run(["curl", "-L", model_url, "-o", VOICE_FILE], check=True)
        subprocess.run(["curl", "-L", config_url, "-o", CONFIG_FILE], check=True)
        
        logger.info(f"Modèle de voix française téléchargé avec succès")

def init_piper():
    """Initialise la voix Piper TTS"""
    global piper_voice
    
    if piper_voice is None:
        # S'assurer que le modèle est téléchargé
        download_voice_model()
        
        # Initialiser la voix
        logger.info(f"Initialisation de la voix Piper...")
        piper_voice = PiperVoice.load(VOICE_FILE, CONFIG_FILE)
        logger.info(f"Voix Piper initialisée avec succès")
    
    return piper_voice

def text_to_speech(text, sentence_silence=0.25):
    """Convertit du texte en audio"""
    voice = init_piper()
    
    # Générer l'audio
    audio_chunks = []
    
    # Diviser le texte en phrases pour une meilleure fluidité
    sentences = text.replace(".", ".^").replace("!", "!^").replace("?", "?^").replace(":", ":^").split("^")
    sentences = [s.strip() for s in sentences if s.strip()]
    
    for sentence in sentences:
        if not sentence:
            continue
            
        logger.debug(f"Synthèse de la phrase: '{sentence}'")
        
        # Synthétiser la phrase
        audio_array = voice.synthesize(sentence)
        audio_chunks.append(audio_array)
        
        # Ajouter un silence entre les phrases
        if sentence_silence > 0:
            silence = np.zeros(int(sentence_silence * voice.sample_rate), dtype=np.int16)
            audio_chunks.append(silence)
    
    # Combiner tous les morceaux audio
    if audio_chunks:
        return np.concatenate(audio_chunks)
    else:
        return np.array([], dtype=np.int16)

def play_audio(audio_data, sample_rate=22050):
    """Joue un tableau audio via sounddevice"""
    try:
        sd.play(audio_data, sample_rate)
        sd.wait()
    except Exception as e:
        logger.error(f"Erreur lors de la lecture audio: {e}")

def audio_worker():
    """Fonction de travail pour traiter la file d'attente audio"""
    global is_speaking, stop_speaking
    
    logger.info("Démarrage du worker audio")
    
    while True:
        # Attendre qu'un élément soit disponible dans la file d'attente
        audio_item = audio_queue.get()
        
        if audio_item is None:
            # Signal de fin
            audio_queue.task_done()
            break
        
        try:
            audio_data, sample_rate = audio_item
            is_speaking = True
            stop_speaking = False
            
            # Jouer l'audio par morceaux pour permettre l'interruption
            chunk_size = int(sample_rate * 0.5)  # 500ms par morceau
            num_chunks = len(audio_data) // chunk_size + (1 if len(audio_data) % chunk_size > 0 else 0)
            
            for i in range(num_chunks):
                if stop_speaking:
                    logger.info("Lecture audio interrompue")
                    break
                
                start_idx = i * chunk_size
                end_idx = min(start_idx + chunk_size, len(audio_data))
                chunk = audio_data[start_idx:end_idx]
                
                sd.play(chunk, sample_rate)
                sd.wait()
            
            is_speaking = False
        except Exception as e:
            logger.error(f"Erreur lors de la lecture audio: {e}")
            is_speaking = False
        
        audio_queue.task_done()

@app.route('/synthesize', methods=['POST'])
def synthesize():
    """Endpoint pour synthétiser du texte en audio"""
    start_time = time.time()
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({"error": "Texte vide"}), 400
    
    logger.info(f"Synthèse demandée: '{text[:50]}...' (tronqué)")
    
    try:
        # Synthétiser le texte
        audio_data = text_to_speech(text)
        
        # Créer un fichier WAV en mémoire
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(22050)  # Taux d'échantillonnage de Piper
            wav_file.writeframes(audio_data.tobytes())
        
        wav_data = wav_io.getvalue()
        
        process_time = time.time() - start_time
        logger.info(f"Synthèse terminée en {process_time:.2f} secondes")
        
        return Response(wav_data, mimetype='audio/wav')
    
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/speak', methods=['POST'])
def speak():
    """Endpoint pour synthétiser et jouer du texte directement"""
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({"error": "Texte vide"}), 400
    
    logger.info(f"Lecture demandée: '{text[:50]}...' (tronqué)")
    
    try:
        # Synthétiser le texte
        audio_data = text_to_speech(text)
        
        # Ajouter à la file d'attente pour lecture
        audio_queue.put((audio_data, 22050))
        
        return jsonify({"status": "queued"})
    
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop():
    """Endpoint pour arrêter la lecture en cours"""
    global stop_speaking
    
    logger.info("Arrêt de la lecture demandé")
    stop_speaking = True
    
    return jsonify({"status": "stopping"})

@app.route('/status', methods=['GET'])
def status():
    """Endpoint pour vérifier l'état du service"""
    return jsonify({
        "status": "running",
        "is_speaking": is_speaking,
        "piper_initialized": piper_voice is not None
    })

@app.route('/stream', methods=['POST'])
def stream():
    """Endpoint pour synthétiser et jouer du texte en streaming"""
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({"error": "Texte vide"}), 400
    
    logger.info(f"Streaming demandé: '{text[:50]}...' (tronqué)")
    
    try:
        # Synthétiser le texte
        audio_data = text_to_speech(text)
        
        # Si une lecture est en cours, l'arrêter
        global stop_speaking
        if is_speaking:
            stop_speaking = True
            time.sleep(0.1)  # Attendre un peu que la lecture s'arrête
        
        # Ajouter à la file d'attente pour lecture
        audio_queue.put((audio_data, 22050))
        
        return jsonify({"status": "streaming"})
    
    except Exception as e:
        logger.error(f"Erreur lors de la synthèse streaming: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Démarrer le thread worker pour la lecture audio
    audio_thread = threading.Thread(target=audio_worker, daemon=True)
    audio_thread.start()
    
    # Initialiser Piper au démarrage
    init_piper()
    
    logger.info(f"Démarrage du service TTS sur le port 5002")
    app.run(host='0.0.0.0', port=5002, threaded=True)