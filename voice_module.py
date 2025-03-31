import numpy as np
import sounddevice as sd
import wave
import tempfile
import os
import subprocess
import threading
import time
import logging
from typing import Optional

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("voice_service.log")]
)
logger = logging.getLogger("voice-module")

class VoiceRecognitionService:
    """Service de reconnaissance vocale intégré"""
    
    def __init__(self):
        # Chemins vers whisper.cpp
        self.whisper_path = "opt/whisper.cpp"
        self.whisper_model = os.path.join(self.whisper_path, "models/ggml-base.bin")
        self.whisper_exec = os.path.join(self.whisper_path, "build/bin/whisper-cli")
        
        # Vérifier les fichiers nécessaires
        if not os.path.exists(self.whisper_model):
            logger.warning(f"Modèle Whisper introuvable: {self.whisper_model}")
        if not os.path.exists(self.whisper_exec):
            logger.warning(f"Exécutable Whisper introuvable: {self.whisper_exec}")
        
        # Paramètres d'enregistrement audio
        self.sample_rate = 16000
        self.channels = 1
        self.dtype = np.int16
        
        # Paramètres de détection
        self.max_record_duration = 60.0  # 60 secondes
        self.min_silence_duration = 1.5  # secondes 
        self.silence_threshold = 0.02
        
        # Variables d'état
        self.recording = False
        self.is_processing = False
        self.audio_data = []
        self.active_recording_thread = None
        self.last_transcription = ""
        
        logger.info("Service de reconnaissance vocale initialisé")
    
    def start_recording(self) -> bool:
        """Démarre l'enregistrement audio"""
        if self.recording:
            logger.warning("Tentative de démarrer un enregistrement déjà en cours")
            return False
        
        self.recording = True
        self.is_processing = True
        logger.info("Démarrage de l'enregistrement...")
        
        # Réinitialiser les données
        self.audio_data = []
        self.last_transcription = ""
        
        # Créer un thread d'enregistrement
        self.active_recording_thread = threading.Thread(target=self._record_audio)
        self.active_recording_thread.start()
        
        return True
    
    def stop_recording(self) -> bool:
        """Arrête l'enregistrement en cours"""
        if not self.recording:
            logger.warning("Tentative d'arrêter un enregistrement qui n'est pas en cours")
            return False
        
        logger.info("Arrêt de l'enregistrement...")
        self.recording = False
        
        # Le traitement continuera dans le thread _record_audio
        return True
    
    def get_transcription(self) -> str:
        """Renvoie la dernière transcription"""
        return self.last_transcription
    
    def _record_audio(self):
        """Fonction d'enregistrement audio avec détection de fin automatique"""
        start_time = time.time()
        logger.info("Début de l'enregistrement audio")
        
        silence_start = None
        
        def callback(indata, frames, time_info, status):
            if status:
                logger.error(f"Erreur d'enregistrement: {status}")
            
            # Stocker les données audio
            self.audio_data.append(indata.copy())
        
        # Démarrer l'enregistrement
        stream = sd.InputStream(samplerate=self.sample_rate, channels=self.channels, 
                               dtype=self.dtype, callback=callback)
        stream.start()
        
        try:
            logger.info("Flux d'enregistrement démarré")
            while self.recording:
                # Vérifier si nous avons dépassé la durée maximum
                current_duration = time.time() - start_time
                if current_duration > self.max_record_duration:
                    logger.info(f"Durée maximum atteinte ({self.max_record_duration}s)")
                    break
                
                # Vérifier le silence si nous avons des données
                if len(self.audio_data) > 0:
                    current_data = self.audio_data[-1]
                    if self._detect_silence(current_data):
                        if silence_start is None:
                            silence_start = time.time()
                            logger.debug("Silence potentiel détecté")
                        elif time.time() - silence_start > self.min_silence_duration:
                            logger.info(f"Silence confirmé pendant {self.min_silence_duration}s, arrêt de l'enregistrement")
                            break
                    else:
                        silence_start = None
                
                time.sleep(0.1)
        
        finally:
            # Arrêter l'enregistrement
            stream.stop()
            stream.close()
            recording_duration = time.time() - start_time
            logger.info(f"Enregistrement terminé après {recording_duration:.2f}s, {len(self.audio_data)} segments capturés")
            
            # Traiter l'audio enregistré
            if len(self.audio_data) > 0:
                try:
                    # Concaténer tous les segments audio
                    audio_concat = np.concatenate(self.audio_data)
                    
                    # Sauvegarder l'audio dans un fichier temporaire
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                        temp_filename = temp_file.name
                        with wave.open(temp_filename, 'wb') as wf:
                            wf.setnchannels(self.channels)
                            wf.setsampwidth(2)  # 16 bits
                            wf.setframerate(self.sample_rate)
                            wf.writeframes(audio_concat.tobytes())
                    
                    logger.info(f"Audio sauvegardé dans {temp_filename}")
                    
                    # Transcrire l'audio
                    logger.info("Début de la transcription")
                    transcription_start = time.time()
                    self.last_transcription = self._transcribe_audio(temp_filename)
                    transcription_time = time.time() - transcription_start
                    
                    logger.info(f"Transcription terminée en {transcription_time:.2f}s")
                    logger.info(f"Transcription: '{self.last_transcription[:100]}...' (tronquée à 100 caractères)")
                    
                    # Supprimer le fichier temporaire
                    os.unlink(temp_filename)
                    logger.debug(f"Fichier temporaire supprimé: {temp_filename}")
                    
                except Exception as e:
                    logger.error(f"Erreur lors du traitement de l'audio: {e}")
            else:
                logger.warning("Aucune donnée audio capturée")
            
            # Marquer la fin du traitement
            self.is_processing = False
    
    def _detect_silence(self, data: np.ndarray) -> bool:
        """Détecte le silence dans un flux audio"""
        # Convertir en valeurs absolues normalisées
        data_norm = np.abs(data.astype(np.float32)) / np.max(np.abs(np.iinfo(self.dtype).max))
        # Vérifier si le niveau est inférieur au seuil
        is_silent = np.max(data_norm) < self.silence_threshold
        return is_silent
    
    def _transcribe_audio(self, audio_file: str) -> str:
        """Transcrit l'audio en utilisant whisper.cpp"""
        try:
            # Préparation de la commande whisper
            cmd = [
                self.whisper_exec,
                "-m", self.whisper_model,
                "-f", audio_file,
                "-l", "fr",  # Langue française
                "--no-timestamps",
                "--no-gpu",  # Pour éviter les problèmes avec Metal sur Mac
                "-t", "4"    # Utiliser 4 threads pour accélérer le traitement
            ]
            
            logger.debug(f"Commande whisper: {' '.join(cmd)}")
            start_time = time.time()
            
            # Exécuter whisper
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Whisper a retourné un code d'erreur: {result.returncode}")
                logger.error(f"Erreur: {result.stderr}")
            
            process_time = time.time() - start_time
            logger.info(f"Traitement whisper.cpp terminé en {process_time:.2f}s")
            
            # Extraire le texte transcrit (ignorer les infos de debug)
            transcription = ""
            for line in result.stdout.splitlines():
                # Filtrer les lignes de log qui commencent par [
                if line and not line.startswith("["):
                    transcription += line.strip() + " "
            
            return transcription.strip()
        
        except Exception as e:
            logger.error(f"Erreur lors de la transcription: {e}")
            return ""
    
    def cleanup(self):
        """Nettoie les ressources (à appeler lors de l'arrêt du programme)"""
        if self.recording:
            self.stop_recording()
            
        # Attendre la fin du thread d'enregistrement
        if self.active_recording_thread and self.active_recording_thread.is_alive():
            self.active_recording_thread.join(timeout=2)
                # Vérifier si nous avons