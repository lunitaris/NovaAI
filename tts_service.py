from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import sounddevice as sd
import logging
import threading
import queue
import sys
from io import BytesIO
import wave
import time

# Vérifier si piper est installé
try:
    from piper import PiperVoice
    PIPER_INSTALLED = True
except ImportError:
    PIPER_INSTALLED = False
    print("Piper TTS n'est pas installé. Installation en cours...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "piper-tts"], check=True)
    from piper import PiperVoice

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("tts_service.log")]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
MODELS_DIR = "tts_models"
VOICE_FILE = f"{MODELS_DIR}/fr_FR-siwis-medium.onnx"
CONFIG_FILE = f"{MODELS_DIR}/fr_FR-siwis-medium.onnx.json"
SAMPLE_RATE = 22050

# Paramètres audio
VOLUME_FACTOR = 0.8  # Réduire le volume pour éviter le clipping
FADE_DURATION = 0.01  # Durée du fade in/out en secondes

# Variables globales
piper_voice = None
audio_queue = queue.Queue()
is_speaking = False
stop_speaking = False

def ensure_voice_model():
    """Télécharge le modèle si nécessaire et initialise la voix"""
    import os
    import subprocess
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    if not os.path.exists(VOICE_FILE) or not os.path.exists(CONFIG_FILE):
        logger.info("Téléchargement du modèle de voix...")
        model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
        config_url = "https://huggingface.co/rhasspy/piper-voices/raw/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
        subprocess.run(["curl", "-L", model_url, "-o", VOICE_FILE], check=True)
        subprocess.run(["curl", "-L", config_url, "-o", CONFIG_FILE], check=True)

    global piper_voice
    if piper_voice is None:
        logger.info("Initialisation de Piper TTS...")
        piper_voice = PiperVoice.load(VOICE_FILE, CONFIG_FILE)
    
    return piper_voice

def segment_text(text):
    """Divise le texte en segments naturels pour une meilleure synthèse"""
    if not text:
        return []
    
    separators = ['.', '!', '?', ':', ';', ',']
    segments = []
    current = ""
    
    for char in text:
        current += char
        if char in separators and (len(current.strip()) > 0):
            segments.append(current.strip())
            current = ""
    
    if current.strip():
        segments.append(current.strip())
        
    return segments

def process_audio(audio_data):
    """Traite l'audio pour réduire le clipping et améliorer la qualité"""
    if len(audio_data) == 0:
        return audio_data
    
    # Convertir en float32 pour le traitement
    audio_float = audio_data.astype(np.float32)
    
    # Réduire l'amplitude pour éviter le clipping
    audio_float *= VOLUME_FACTOR
    
    # Appliquer un fade in/out pour éviter les clics
    fade_samples = int(FADE_DURATION * SAMPLE_RATE)
    if fade_samples > 0 and len(audio_float) > 2 * fade_samples:
        # Fade in
        fade_in = np.linspace(0.0, 1.0, fade_samples)
        audio_float[:fade_samples] *= fade_in
        
        # Fade out
        fade_out = np.linspace(1.0, 0.0, fade_samples)
        audio_float[-fade_samples:] *= fade_out
    
    return audio_float.astype(np.int16)

def synthesize_text(text):
    """Synthétise du texte en audio sans fichiers temporaires"""
    voice = ensure_voice_model()
    
    # Diviser en segments pour une synthèse plus naturelle
    segments = segment_text(text)
    all_audio = []
    
    for segment in segments:
        if not segment:
            continue
            
        # Synthétiser directement en mémoire
        memory_file = BytesIO()
        wav_buffer = wave.open(memory_file, 'wb')
        wav_buffer.setnchannels(1)
        wav_buffer.setsampwidth(2)
        wav_buffer.setframerate(SAMPLE_RATE)
        
        voice.synthesize(segment, wav_buffer)
        
        # Récupérer les données audio sans fichier temporaire
        memory_file.seek(0)
        wav_reader = wave.open(memory_file, 'rb')
        audio_data = np.frombuffer(wav_reader.readframes(wav_reader.getnframes()), dtype=np.int16)
        
        # Traiter l'audio pour éviter le clipping
        processed_audio = process_audio(audio_data)
        all_audio.append(processed_audio)
        
        # Ajouter un court silence entre les segments
        silence_duration = 0.2  # secondes
        all_audio.append(np.zeros(int(silence_duration * SAMPLE_RATE), dtype=np.int16))
    
    # Combinaison de tous les segments audio
    if all_audio:
        return np.concatenate(all_audio)
    else:
        return np.array([], dtype=np.int16)

def audio_playback_worker():
    """Thread worker pour la lecture audio"""
    global is_speaking, stop_speaking
    
    logger.info("Démarrage du worker de lecture audio")
    
    while True:
        audio_item = audio_queue.get()
        
        if audio_item is None:
            # Signal de fin
            audio_queue.task_done()
            break
        
        try:
            audio_data = audio_item
            is_speaking = True
            stop_speaking = False
            
            # Jouer l'audio complet d'un coup plutôt que par morceaux
            # pour éviter les problèmes de transitions
            sd.play(audio_data, SAMPLE_RATE)
            
            # Attendre que la lecture soit terminée ou interrompue
            while sd.get_stream().active and not stop_speaking:
                time.sleep(0.1)
                
            # Si on demande d'arrêter pendant la lecture
            if stop_speaking:
                sd.stop()
                logger.info("Lecture interrompue")
            
        except Exception as e:
            logger.error(f"Erreur de lecture audio: {e}")
        finally:
            is_speaking = False
            audio_queue.task_done()

@app.route('/speak', methods=['POST'])
def speak():
    """Endpoint pour la synthèse vocale"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "Texte vide"}), 400
        
        logger.info(f"Synthèse demandée: {text}")
        
        # Synthétiser le texte
        audio_data = synthesize_text(text)
        
        # Mettre en file d'attente pour lecture
        audio_queue.put(audio_data)
        
        return jsonify({"status": "success", "length": len(audio_data)})
        
    except Exception as e:
        logger.error(f"Erreur de synthèse: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/stream', methods=['POST'])
def stream():
    """Stream audio par phrases pour une réponse plus rapide"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({"error": "Texte vide"}), 400
        
        logger.info(f"Stream demandé: {text}")
        
        # Pas de segmentation côté serveur - laissons le client gérer cela
        audio_data = synthesize_text(text)
        audio_queue.put(audio_data)
        
        return jsonify({"status": "success"})
        
    except Exception as e:
        logger.error(f"Erreur de stream: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop():
    """Arrête la lecture audio en cours"""
    global stop_speaking
    
    logger.info("Arrêt de la synthèse demandé")
    stop_speaking = True
    
    # Vider la file d'attente pour éviter la lecture des segments en attente
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
            audio_queue.task_done()
        except queue.Empty:
            break
    
    return jsonify({"status": "stopped"})

@app.route('/status', methods=['GET'])
def status():
    """État du service"""
    return jsonify({
        "status": "running",
        "is_speaking": is_speaking,
        "model_loaded": piper_voice is not None
    })

if __name__ == '__main__':
    # Initialisation du modèle au démarrage
    ensure_voice_model()
    
    # Démarrer le thread de lecture audio
    audio_thread = threading.Thread(target=audio_playback_worker, daemon=True)
    audio_thread.start()
    
    logger.info("Service TTS démarré sur le port 5002")
    app.run(host='0.0.0.0', port=5002, threaded=True)