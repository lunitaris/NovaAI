import numpy as np
import sounddevice as sd
import logging
import threading
import queue
import io
import wave
import os
import time
import asyncio
from typing import List, Optional

# Vérifier si piper est installé
try:
    from piper import PiperVoice
    PIPER_INSTALLED = True
except ImportError:
    PIPER_INSTALLED = False
    import subprocess
    import sys
    print("Piper TTS n'est pas installé. Installation en cours...")
    subprocess.run([sys.executable, "-m", "pip", "install", "piper-tts"], check=True)
    from piper import PiperVoice

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("tts_service.log")]
)
logger = logging.getLogger("tts-module")

class TTSService:
    """Service de synthèse vocale intégré"""
    
    def __init__(self):
        # Configuration
        self.models_dir = "tts_models"
        self.voice_file = f"{self.models_dir}/fr_FR-siwis-medium.onnx"
        self.config_file = f"{self.models_dir}/fr_FR-siwis-medium.onnx.json"
        self.sample_rate = 22050
        
        # État du service
        self.voice = None
        self.audio_queue = queue.Queue()
        self.is_speaking = False
        self.stop_requested = False
        
        # Paramètres audio
        self.volume_factor = 0.8  # Réduire le volume pour éviter le clipping
        self.fade_duration = 0.01  # Durée du fade in/out en secondes
        
        # Buffer de texte pour éviter les synthèses fragmentées
        self.text_buffer = ""
        self.last_synthesis_time = 0
        self.min_synthesis_interval = 0.2  # Réduit pour améliorer la fluidité
        
        # Pour la synthèse de longues phrases
        self.current_paragraph = ""
        
        # Initialiser le modèle de voix
        self._init_voice()
        
        # Démarrer le thread de lecture audio
        self.audio_thread = threading.Thread(target=self._audio_playback_worker, daemon=True)
        self.audio_thread.start()
        
        logger.info("Service de synthèse vocale initialisé")
    
    def _init_voice(self):
        """Initialise le modèle de voix"""
        try:
            # Vérifier si le dossier des modèles existe
            os.makedirs(self.models_dir, exist_ok=True)
            
            # Télécharger le modèle s'il n'existe pas
            if not os.path.exists(self.voice_file) or not os.path.exists(self.config_file):
                logger.info("Téléchargement du modèle de voix en cours...")
                self._download_model()
            
            # Charger le modèle
            logger.info("Chargement du modèle de voix...")
            self.voice = PiperVoice.load(self.voice_file, self.config_file)
            logger.info("Modèle de voix chargé avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du modèle de voix: {e}")
            raise
    
    def _download_model(self):
        """Télécharge le modèle de voix français"""
        try:
            import urllib.request
            
            # URLs des fichiers
            model_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
            config_url = "https://huggingface.co/rhasspy/piper-voices/raw/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
            
            # Télécharger les fichiers
            logger.info(f"Téléchargement du modèle depuis {model_url}")
            urllib.request.urlretrieve(model_url, self.voice_file)
            
            logger.info(f"Téléchargement de la configuration depuis {config_url}")
            urllib.request.urlretrieve(config_url, self.config_file)
            
            logger.info("Téléchargement du modèle terminé")
            
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement du modèle: {e}")
            raise
    
    async def synthesize(self, text: str):
        """Synthétise le texte en audio avec buffer intelligent"""
        if not text or not text.strip():
            return
        
        try:
            # Ajouter le texte au buffer
            self.text_buffer += text
            
            # Déterminer si on doit synthétiser maintenant
            should_synthesize = False
            
            # Vérifier si le texte contient une frontière naturelle
            primary_boundaries = ['.', '!', '?', '\n']
            secondary_boundaries = [':', ';']
            
            # Synthétiser immédiatement si frontière primaire
            if any(boundary in text for boundary in primary_boundaries):
                should_synthesize = True
            # Synthétiser avec une pause plus courte si frontière secondaire
            elif any(boundary in text for boundary in secondary_boundaries):
                should_synthesize = True
                # Pause plus courte pour les délimiteurs légers
                self.min_synthesis_interval = 0.1
            # Si le buffer est assez grand pour former une phrase complète
            elif len(self.text_buffer.split()) > 12:
                should_synthesize = True
                
            # Respecter l'intervalle minimum entre les synthèses
            current_time = time.time()
            if current_time - self.last_synthesis_time < self.min_synthesis_interval:
                should_synthesize = False
                
            if should_synthesize:
                buffer_text = self.text_buffer.strip()
                
                # Traiter les listes à puces et les astérisques pour améliorer la prosodie
                buffer_text = self._preprocess_text(buffer_text)
                
                logger.info(f"Synthèse demandée: {buffer_text[:100]}{'...' if len(buffer_text) > 100 else ''}")
                
                # Segmenter intelligemment
                segments = self._segment_text(buffer_text)
                
                # Générer et mettre en file d'attente chaque segment
                for segment in segments:
                    if segment.strip():
                        # Exécuter dans un thread pour ne pas bloquer
                        audio_data = await asyncio.to_thread(self._generate_audio, segment.strip())
                        if audio_data is not None and len(audio_data) > 0:
                            self.audio_queue.put(audio_data)
                
                # Réinitialiser le buffer
                self.text_buffer = ""
                self.last_synthesis_time = current_time
                
                # Réinitialiser l'intervalle par défaut
                self.min_synthesis_interval = 0.2
        
        except Exception as e:
            logger.error(f"Erreur lors de la synthèse: {e}")
    
    def _preprocess_text(self, text: str) -> str:
        """Prétraite le texte pour améliorer la prosodie"""
        # Remplacer les puces par du texte plus parlant
        text = text.replace("* ", ", point: ")
        text = text.replace("- ", ", tiret: ")
        
        # Améliorer la lecture des URL et symboles spéciaux
        text = text.replace("http://", "h t t p deux-points slash slash ")
        text = text.replace("https://", "h t t p s deux-points slash slash ")
        text = text.replace("www.", "w w w point ")
        
        # Traiter les parenthèses pour mieux marquer les pauses
        text = text.replace("(", ", ouverture de parenthèse, ")
        text = text.replace(")", ", fermeture de parenthèse, ")
        
        # Normaliser les espaces
        text = ' '.join(text.split())
        
        return text

    def _segment_text(self, text: str) -> List[str]:
        """Divise le texte en segments naturels pour une meilleure synthèse"""
        if not text:
            return []
        
        # Nettoyer le texte (espaces multiples, etc.)
        text = ' '.join(text.split())
        
        # Une seule phrase courte = un seul segment
        if len(text.split()) < 15 and not any(marker in text for marker in ['.', '!', '?', ':', ';', '\n']):
            return [text]
        
        # Délimiteurs primaires (forte pause)
        primary_markers = ['.', '!', '?', '\n']
        # Délimiteurs secondaires (pause légère)
        secondary_markers = [':', ';', ',']
        
        # Découper d'abord par les délimiteurs primaires
        primary_segments = []
        current = ""
        
        for char in text:
            current += char
            if char in primary_markers:
                primary_segments.append(current.strip())
                current = ""
        
        if current:
            primary_segments.append(current.strip())
        
        # Puis découper les segments trop longs par les délimiteurs secondaires
        final_segments = []
        for segment in primary_segments:
            if len(segment.split()) > 15:  # Segments trop longs
                subsegments = []
                subcurrent = ""
                
                for char in segment:
                    subcurrent += char
                    if char in secondary_markers:
                        if len(subcurrent.split()) > 5:  # Éviter les segments trop courts
                            subsegments.append(subcurrent.strip())
                            subcurrent = ""
                
                if subcurrent:
                    subsegments.append(subcurrent.strip())
                    
                final_segments.extend(subsegments)
            else:
                final_segments.append(segment)
        
        return final_segments

    def _generate_audio(self, text: str) -> Optional[np.ndarray]:
        """Génère l'audio à partir du texte"""
        if not text or not self.voice:
            return None
            
        try:
            # Générer l'audio directement en mémoire
            with io.BytesIO() as buf:
                wav_file = wave.open(buf, 'wb')
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16 bits
                wav_file.setframerate(self.sample_rate)
                
                # Synthétiser avec Piper
                self.voice.synthesize(text, wav_file)
                wav_file.close()
                
                # Récupérer les données audio
                buf.seek(0)
                with wave.open(buf, 'rb') as wf:
                    audio_data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            
            # Traiter l'audio pour améliorer la qualité
            processed_audio = self._process_audio(audio_data)
            return processed_audio
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération audio: {e}")
            return None
    
    def _process_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Traite l'audio pour réduire le clipping et améliorer la qualité"""
        if len(audio_data) == 0:
            return audio_data
        
        # Convertir en float32 pour le traitement
        audio_float = audio_data.astype(np.float32)
        
        # Réduire l'amplitude pour éviter le clipping
        audio_float *= self.volume_factor
        
        # Appliquer un fade in/out pour éviter les clics
        fade_samples = int(self.fade_duration * self.sample_rate)
        if fade_samples > 0 and len(audio_float) > 2 * fade_samples:
            # Fade in
            fade_in = np.linspace(0.0, 1.0, fade_samples)
            audio_float[:fade_samples] *= fade_in
            
            # Fade out
            fade_out = np.linspace(1.0, 0.0, fade_samples)
            audio_float[-fade_samples:] *= fade_out
        
        return audio_float.astype(np.int16)
    
    def _audio_playback_worker(self):
        """Thread worker pour la lecture audio"""
        logger.info("Démarrage du worker de lecture audio")
        
        while True:
            try:
                # Récupérer le prochain segment audio
                audio_data = self.audio_queue.get()
                
                # None est un signal d'arrêt
                if audio_data is None:
                    self.audio_queue.task_done()
                    break
                
                # Jouer l'audio
                self.is_speaking = True
                self.stop_requested = False
                
                # Jouer l'audio sans délai préalable pour rendre la lecture plus fluide
                sd.play(audio_data, self.sample_rate)
                
                # Attendre la fin de la lecture (méthode plus efficace)
                sd.wait()
                
                # Ajouter un très léger délai pour la pause naturelle
                time.sleep(0.05)
                    
                # Arrêter la lecture si demandé
                if self.stop_requested:
                    sd.stop()
                    logger.info("Lecture interrompue")
                
                self.is_speaking = False
                self.audio_queue.task_done()
                
            except Exception as e:
                logger.error(f"Erreur dans le worker de lecture: {e}")
                self.is_speaking = False
                self.audio_queue.task_done()
    
    def stop(self):
        """Arrête la lecture audio en cours"""
        logger.info("Arrêt de la synthèse demandé")
        self.stop_requested = True
        
        # Vider la file d'attente
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except queue.Empty:
                break
        
        # Réinitialiser le buffer de texte
        self.text_buffer = ""
    
    def cleanup(self):
        """Nettoie les ressources (à appeler lors de l'arrêt du programme)"""
        logger.info("Nettoyage des ressources TTS")
        self.stop()
        
        # Signaler au thread de s'arrêter
        self.audio_queue.put(None)
        
        # Attendre la fin du thread
        if self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)