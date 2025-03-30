from flask import Flask, request, jsonify
from flask_cors import CORS
import tempfile
import os
import subprocess
import sounddevice as sd
import numpy as np
import wave
import time
import threading
import logging

# Configuration du logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Activer CORS pour permettre les requêtes depuis notre interface

# Chemins vers whisper.cpp
WHISPER_PATH = "opt/whisper.cpp"
WHISPER_MODEL = os.path.join(WHISPER_PATH, "models/ggml-base.bin")
WHISPER_EXEC = os.path.join(WHISPER_PATH, "build/bin/whisper-cli")

# Paramètres d'enregistrement audio
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16
SILENCE_THRESHOLD = 0.03
MIN_SILENCE_DURATION = 1.0  # secondes
MAX_RECORD_DURATION = 30.0  # secondes maximum d'enregistrement

# Variables globales pour contrôler l'enregistrement
recording = False
audio_data = []
active_recording_thread = None
last_transcription = ""

def detect_silence(data, threshold=SILENCE_THRESHOLD, duration=MIN_SILENCE_DURATION):
    """Détecte le silence dans un flux audio"""
    # Convertir en valeurs absolues normalisées
    data_norm = np.abs(data.astype(np.float32)) / np.max(np.abs(np.iinfo(DTYPE).max))
    # Vérifier si le niveau est inférieur au seuil
    is_silent = np.max(data_norm) < threshold
    return is_silent

def record_audio():
    """Fonction d'enregistrement audio avec détection de fin automatique"""
    global recording, audio_data, last_transcription
    
    # Réinitialiser les données
    audio_data = []
    last_transcription = ""
    silence_start = None
    start_time = time.time()
    
    def callback(indata, frames, time_info, status):
        if status:
            logger.error(f"Erreur: {status}")
        
        # Stocker les données audio
        audio_data.append(indata.copy())
    
    # Démarrer l'enregistrement
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, callback=callback)
    stream.start()
    
    try:
        logger.info("Enregistrement démarré...")
        while recording:
            # Vérifier si nous avons dépassé la durée maximum
            if time.time() - start_time > MAX_RECORD_DURATION:
                logger.info("Durée maximum atteinte.")
                break
            
            # Vérifier le silence si nous avons des données
            if len(audio_data) > 0:
                current_data = audio_data[-1]
                if detect_silence(current_data):
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > MIN_SILENCE_DURATION:
                        logger.info("Silence détecté, arrêt de l'enregistrement.")
                        break
                else:
                    silence_start = None
            
            time.sleep(0.1)
    
    finally:
        stream.stop()
        stream.close()
        logger.info(f"Enregistrement terminé, {len(audio_data)} segments capturés")
        
        if len(audio_data) > 0:
            # Sauvegarder l'audio dans un fichier temporaire
            audio_concat = np.concatenate(audio_data)
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_filename = temp_file.name
                with wave.open(temp_filename, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)  # 16 bits
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(audio_concat.tobytes())
            
            logger.info(f"Audio sauvegardé dans {temp_filename}")
            
            # Transcrire l'audio
            transcription = transcribe_audio(temp_filename)
            # Stocker la transcription dans la variable globale
            last_transcription = transcription
            logger.info(f"Transcription obtenue: '{last_transcription}'")
            
            # Supprimer le fichier temporaire
            os.unlink(temp_filename)
            
            return transcription
        
        return ""

def transcribe_audio(audio_file):
    """Transcrit l'audio en utilisant whisper.cpp"""
    try:
        cmd = [
            WHISPER_EXEC,
            "-m", WHISPER_MODEL,
            "-f", audio_file,
            "-l", "fr",      # Détection automatique de la langue
            "--no-timestamps",  # Ne pas inclure les timestamps
            "--no-gpu"
        ]
        
        logger.debug(f"Commande whisper: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        logger.debug(f"Sortie de whisper: {result.stdout}")
        if result.stderr:
            logger.error(f"Erreurs de whisper: {result.stderr}")
        
        # Extraire seulement le texte transcrit (ignorer les infos de debug)
        transcription = ""
        for line in result.stdout.splitlines():
            if line and not line.startswith("["):  # Ignorer les lignes de log
                transcription += line.strip() + " "
        
        transcription = transcription.strip()
        logger.info(f"Transcription finale: '{transcription}'")
        return transcription
    
    except Exception as e:
        logger.error(f"Erreur lors de la transcription: {e}")
        return ""

@app.route('/start-recording', methods=['POST'])
def start_recording():
    global recording, active_recording_thread
    
    if not recording:
        recording = True
        logger.info("Démarrage de l'enregistrement...")
        
        # Créer un vrai thread d'enregistrement qui appelle record_audio
        active_recording_thread = threading.Thread(target=record_audio)
        active_recording_thread.start()
        
        return jsonify({"status": "started"})
    
    return jsonify({"status": "already_recording"})

@app.route('/stop-recording', methods=['POST'])
def stop_recording():
    global recording, active_recording_thread
    
    if recording:
        logger.info("Arrêt de l'enregistrement...")
        recording = False
        
        # On ne fait rien d'autre ici, car record_audio() est déjà en cours d'exécution
        # et terminera son traitement une fois que recording=False
        
        return jsonify({"status": "processing"})
    
    return jsonify({"status": "not_recording"})

@app.route('/get-transcription', methods=['GET'])
def get_transcription():
    global last_transcription
    
    logger.info(f"Envoi de la transcription: '{last_transcription}'")
    return jsonify({"text": last_transcription})

if __name__ == '__main__':
    logger.info("Démarrage du service de reconnaissance vocale sur le port 5001")
    app.run(host='0.0.0.0', port=5001)