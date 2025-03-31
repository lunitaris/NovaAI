from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import tempfile
import os
import subprocess
import numpy as np
import sounddevice as sd
import time
import wave
import threading
import logging
import queue
import sys

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
CORS(app)

# Configuration de Piper TTS
MODELS_DIR = "tts_models"
VOICE_FILE = os.path.join(MODELS_DIR, "fr_FR-siwis-medium.onnx")
CONFIG_FILE = os.path.join(MODELS_DIR, "fr_FR-siwis-medium.onnx.json")
os.makedirs(MODELS_DIR, exist_ok=True)

# Variables globales
piper_voice = None
audio_queue = queue.Queue()
is_speaking = False
stop_speaking = False

def download_voice_model():
    """Télécharge le modèle de voix française si nécessaire"""
    if not os.path.exists(VOICE_FILE) or not os.path.exists(CONFIG_FILE):
        logger.info("Téléchargement du modèle de voix française...")
        model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
        config_url = "https://huggingface.co/rhasspy/piper-voices/raw/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
        subprocess.run(["curl", "-L", model_url, "-o", VOICE_FILE], check=True)
        subprocess.run(["curl", "-L", config_url, "-o", CONFIG_FILE], check=True)
        logger.info("Modèle téléchargé avec succès")

def init_piper():
    """Initialise la voix Piper TTS"""
    global piper_voice
    if piper_voice is None:
        download_voice_model()
        logger.info("Initialisation de la voix Piper...")
        piper_voice = PiperVoice.load(VOICE_FILE, CONFIG_FILE)
        logger.info("Voix Piper initialisée")
    return piper_voice

def text_to_speech(text):
    """Convertit le texte en audio en utilisant Piper"""
    voice = init_piper()
    
    # Diviser le texte en phrases pour une meilleure fluidité
    sentences = text.replace(".", ".^").replace("!", "!^").replace("?", "?^").replace(":", ":^").split("^")
    sentences = [s.strip() for s in sentences if s.strip()]
    
    all_audio = []
    for sentence in sentences:
        if not sentence:
            continue
            
        logger.debug(f"Synthèse de la phrase: '{sentence}'")
        
        # Utiliser un objet wave en mémoire
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_filename = temp_file.name
            
        # Ouvrir le fichier wav en écriture et synthétiser
        with wave.open(temp_filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)  # Fréquence standard de Piper
            audio_array = voice.synthesize(sentence, wav_file)
            
        # Lire l'audio du fichier
        with wave.open(temp_filename, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
            all_audio.append(audio)
            
        # Supprimer le fichier temporaire
        os.unlink(temp_filename)
        
        # Ajouter un silence entre les phrases (0.25 secondes)
        silence = np.zeros(int(0.25 * 22050), dtype=np.int16)
        all_audio.append(silence)
    
    # Combiner toutes les phrases
    if all_audio:
        return np.concatenate(all_audio)
    else:
        return np.array([], dtype=np.int16)

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
            
            for i in range(0, len(audio_data), chunk_size):
                if stop_speaking:
                    logger.info("Lecture audio interrompue")
                    break
                
                chunk = audio_data[i:min(i + chunk_size, len(audio_data))]
                sd.play(chunk, sample_rate)
                sd.wait()
            
            is_speaking = False
        except Exception as e:
            logger.error(f"Erreur lors de la lecture audio: {e}")
            is_speaking = False
        
        audio_queue.task_done()

@app.route('/speak', methods=['POST'])
def speak():
    """Endpoint pour synthétiser et jouer du texte"""
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

@app.route('/stream', methods=['POST'])
def stream():
    """Endpoint pour synthétiser et jouer du texte en streaming (utilise la même méthode que speak)"""
    return speak()

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

@app.route('/test', methods=['GET'])
def test():
    """Endpoint de test simple pour vérifier le fonctionnement de Piper"""
    try:
        voice = init_piper()
        test_text = "Bonjour."
        
        logger.info(f"Test de synthèse avec texte court: '{test_text}'")
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_filename = temp_file.name
            
        with wave.open(temp_filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            voice.synthesize(test_text, wav_file)
            
        if os.path.exists(temp_filename):
            logger.info(f"Fichier créé avec succès, taille: {os.path.getsize(temp_filename)} octets")
            os.unlink(temp_filename)
            return jsonify({"status": "success", "message": "Test réussi"})
        else:
            return jsonify({"status": "error", "message": "Fichier non créé"}), 500
    except Exception as e:
        logger.error(f"Erreur lors du test: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Démarrer le thread worker pour la lecture audio
    audio_thread = threading.Thread(target=audio_worker, daemon=True)
    audio_thread.start()
    
    # Initialiser Piper au démarrage
    init_piper()
    
    logger.info(f"Démarrage du service TTS sur le port 5002")
    app.run(host='0.0.0.0', port=5002, threaded=True)