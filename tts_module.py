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
from typing import List, Optional, Dict, Any
from collections import deque
import re

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

class PCMStreamingBuffer:
    """Buffer circulaire pour streaming PCM."""
    
    def __init__(self, max_size=1048576):  # 1MB buffer par défaut
        self.buffer = np.zeros(max_size, dtype=np.int16)
        self.max_size = max_size
        self.write_pos = 0
        self.read_pos = 0
        self.available_data = 0
        self.lock = threading.RLock()
        self.data_available = threading.Event()
        self.finished = False
    
    def write(self, data: np.ndarray) -> int:
        """Écrit des données dans le buffer circulaire."""
        if data.size == 0:
            return 0
            
        with self.lock:
            # Calculer l'espace disponible
            space_available = self.max_size - self.available_data
            write_size = min(data.size, space_available)
            
            if write_size == 0:
                return 0  # Buffer plein
                
            # Écrire les données
            first_chunk_size = min(write_size, self.max_size - self.write_pos)
            self.buffer[self.write_pos:self.write_pos + first_chunk_size] = data[:first_chunk_size]
            
            # Si on atteint la fin du buffer, continuer au début
            if first_chunk_size < write_size:
                second_chunk_size = write_size - first_chunk_size
                self.buffer[:second_chunk_size] = data[first_chunk_size:write_size]
                self.write_pos = second_chunk_size
            else:
                self.write_pos = (self.write_pos + first_chunk_size) % self.max_size
            
            # Mettre à jour le compteur de données disponibles
            self.available_data += write_size
            
            # Signaler que des données sont disponibles
            self.data_available.set()
            
            return write_size
    
    def read(self, size: int) -> np.ndarray:
        """Lit des données du buffer circulaire."""
        with self.lock:
            # Calculer combien de données on peut réellement lire
            read_size = min(size, self.available_data)
            
            if read_size == 0:
                return np.array([], dtype=np.int16)
                
            # Lire les données
            result = np.zeros(read_size, dtype=np.int16)
            first_chunk_size = min(read_size, self.max_size - self.read_pos)
            result[:first_chunk_size] = self.buffer[self.read_pos:self.read_pos + first_chunk_size]
            
            # Si on atteint la fin du buffer, continuer au début
            if first_chunk_size < read_size:
                second_chunk_size = read_size - first_chunk_size
                result[first_chunk_size:] = self.buffer[:second_chunk_size]
                self.read_pos = second_chunk_size
            else:
                self.read_pos = (self.read_pos + first_chunk_size) % self.max_size
            
            # Mettre à jour le compteur de données disponibles
            self.available_data -= read_size
            
            # Si le buffer est vide et qu'on a fini d'écrire, réinitialiser l'événement
            if self.available_data == 0 and self.finished:
                self.data_available.clear()
            elif self.available_data > 0:
                self.data_available.set()
                
            return result
    
    def clear(self):
        """Vide le buffer."""
        with self.lock:
            self.write_pos = 0
            self.read_pos = 0
            self.available_data = 0
            self.data_available.clear()
            self.finished = False
    
    def mark_finished(self):
        """Marque la fin de l'écriture dans le buffer."""
        with self.lock:
            self.finished = True
            if self.available_data == 0:
                self.data_available.clear()
    
    def get_available(self) -> int:
        """Retourne le nombre d'échantillons disponibles."""
        with self.lock:
            return self.available_data
    
    def wait_for_data(self, timeout=None) -> bool:
        """Attend que des données soient disponibles."""
        return self.data_available.wait(timeout)
    
    def is_finished(self) -> bool:
        """Vérifie si la lecture est terminée."""
        with self.lock:
            return self.finished and self.available_data == 0

class TTSService:
    """Service de synthèse vocale intégré avec streaming PCM"""
    
    def __init__(self):
        # Configuration
        self.models_dir = "tts_models"
        self.voice_file = f"{self.models_dir}/fr_FR-siwis-medium.onnx"
        self.config_file = f"{self.models_dir}/fr_FR-siwis-medium.onnx.json"
        self.sample_rate = 22050
        
        # État du service
        self.voice = None
        self.pcm_buffer = PCMStreamingBuffer(max_size=4194304)  # 4MB buffer
        self.is_speaking = False
        self.stop_requested = False
        
        # Thread de lecture audio
        self.audio_thread = None
        self.synthesis_threads = set()
        
        # Buffer de texte pour accumulation
        self.text_buffer = ""
        self.text_buffer_lock = threading.RLock()
        self.last_synthesis_time = 0
        self.min_synthesis_interval = 0.1
        
        # Options de segmentation
        self.initial_segment_threshold = 15  # mots
        self.normal_segment_threshold = 50   # mots
        
        # Initialiser le modèle de voix
        self._init_voice()
        
        # Démarrer le thread de lecture audio
        self.audio_thread = threading.Thread(target=self._audio_playback_worker, daemon=True)
        self.audio_thread.start()
        
        logger.info("Service de synthèse vocale avec streaming PCM initialisé")
    
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
        """Gère l'accumulation de texte et lance la synthèse si nécessaire."""
        if not text or not text.strip():
            return
        
        with self.text_buffer_lock:
            # Ajouter le texte au buffer
            self.text_buffer += text
            
            # Déterminer si on doit synthétiser maintenant
            should_synthesize = False
            segment_threshold = self.initial_segment_threshold if not self.is_speaking else self.normal_segment_threshold
            
            # Vérifier si le texte contient une frontière naturelle
            primary_boundaries = ['.', '!', '?', '\n']
            secondary_boundaries = [':', ';']
            
            # Vérifier la présence de frontières naturelles et si le buffer est assez grand
            contains_primary = any(b in self.text_buffer for b in primary_boundaries)
            contains_secondary = any(b in self.text_buffer for b in secondary_boundaries)
            word_count = len(self.text_buffer.split())
            
            # Synthétiser dans différentes conditions
            if contains_primary and word_count >= 5:
                should_synthesize = True
            elif contains_secondary and word_count >= 10:
                should_synthesize = True
            elif word_count >= segment_threshold:
                should_synthesize = True
                
            # Respecter l'intervalle minimum entre les synthèses
            current_time = time.time()
            min_interval = self.min_synthesis_interval
            if current_time - self.last_synthesis_time < min_interval:
                should_synthesize = False
                
            if should_synthesize:
                text_to_synthesize = self.text_buffer.strip()
                self.text_buffer = ""
                self.last_synthesis_time = current_time
                
                # Lancer la synthèse dans un thread séparé
                synthesis_thread = threading.Thread(
                    target=self._run_synthesis,
                    args=(text_to_synthesize,),
                    daemon=True
                )
                self.synthesis_threads.add(synthesis_thread)
                synthesis_thread.start()
    
    def _run_synthesis(self, text: str):
        """Exécute la synthèse vocale dans un thread séparé."""
        try:
            logger.info(f"Synthèse démarrée: {text[:100]}{'...' if len(text) > 100 else ''}")
            
            # Prétraiter le texte
            processed_text = self._preprocess_text(text)
            
            # Segmenter le texte
            segments = self._segment_text(processed_text)
            
            # Synthétiser chaque segment
            for segment in segments:
                if self.stop_requested:
                    break
                    
                if segment.strip():
                    # Générer l'audio pour ce segment
                    audio_data = self._generate_audio(segment.strip())
                    
                    if audio_data is not None and len(audio_data) > 0:
                        # Traitement audio (normalisation, fade in/out, etc.)
                        processed_audio = self._process_audio(audio_data)
                        
                        # Écrire dans le buffer PCM (avec retries si buffer plein)
                        self._write_to_pcm_buffer(processed_audio)
            
            logger.info(f"Synthèse terminée: {text[:50]}...")
        except Exception as e:
            logger.error(f"Erreur lors de la synthèse: {e}")
        finally:
            # Retirer ce thread de l'ensemble des threads actifs
            self.synthesis_threads.discard(threading.current_thread())
    
    def _write_to_pcm_buffer(self, audio_data: np.ndarray, max_retries=5):
        """Écrit des données audio dans le buffer PCM, avec retries si nécessaire."""
        if audio_data is None or len(audio_data) == 0:
            return
            
        # Marquer que nous sommes en train de parler
        self.is_speaking = True
        
        # Tentatives d'écriture
        data_remaining = audio_data
        retries = 0
        
        while len(data_remaining) > 0 and retries < max_retries and not self.stop_requested:
            written = self.pcm_buffer.write(data_remaining)
            
            if written == 0:
                # Buffer plein, attendre un peu
                retries += 1
                time.sleep(0.1)
            else:
                # Mettre à jour les données restantes
                data_remaining = data_remaining[written:]
                retries = 0  # Réinitialiser le compteur de retries
    
    def _preprocess_text(self, text: str) -> str:
        """Prétraite le texte pour améliorer la prosodie."""
        # Remplacer les puces par du texte plus parlant
        text = text.replace("* ", ", point: ")
        text = text.replace("- ", ", tiret: ")
        
        # Traiter les astérisques pour l'emphase
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Supprimer les ** pour le gras
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Supprimer les * pour l'italique
        
        # Améliorer la lecture des URL et symboles spéciaux
        text = text.replace("http://", "h t t p deux-points slash slash ")
        text = text.replace("https://", "h t t p s deux-points slash slash ")
        text = text.replace("www.", "w w w point ")
        
        # Traiter les parenthèses pour mieux marquer les pauses
        text = text.replace("(", ", ")
        text = text.replace(")", ", ")
        
        # Normaliser les espaces
        text = ' '.join(text.split())
        
        return text
    
    def _segment_text(self, text: str) -> List[str]:
        """Divise le texte en segments naturels pour une meilleure synthèse."""
        if not text:
            return []
            
        # Nettoyer le texte (espaces multiples, etc.)
        text = ' '.join(text.split())
        
        # Une seule phrase courte = un seul segment
        if len(text.split()) < 12 and not any(marker in text for marker in ['.', '!', '?', ':', ';', '\n']):
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
                if current.strip():
                    primary_segments.append(current.strip())
                current = ""
        
        if current.strip():
            primary_segments.append(current.strip())
        
        # Puis découper les segments trop longs par les délimiteurs secondaires
        final_segments = []
        for segment in primary_segments:
            if len(segment.split()) > 20:  # Segments trop longs
                subsegments = []
                subcurrent = ""
                
                for char in segment:
                    subcurrent += char
                    if char in secondary_markers and len(subcurrent.split()) > 5:
                        subsegments.append(subcurrent.strip())
                        subcurrent = ""
                
                if subcurrent.strip():
                    subsegments.append(subcurrent.strip())
                
                final_segments.extend(subsegments)
            else:
                final_segments.append(segment)
        
        return final_segments
    
    def _generate_audio(self, text: str) -> Optional[np.ndarray]:
        """Génère l'audio à partir du texte."""
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
            
            return audio_data
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération audio: {e}")
            return None
    
    def _process_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Traite l'audio pour améliorer la qualité."""
        if len(audio_data) == 0:
            return audio_data
            
        # Convertir en float32 pour le traitement
        audio_float = audio_data.astype(np.float32)
        
        # Normalisation pour éviter le clipping
        max_value = np.max(np.abs(audio_float))
        if max_value > 0:
            # Normaliser à 80% du maximum pour éviter le clipping
            audio_float = audio_float * (0.8 * 32767 / max_value)
        
        # Appliquer un fade in/out pour éviter les clics
        fade_samples = int(0.01 * self.sample_rate)  # 10ms fade
        if fade_samples > 0 and len(audio_float) > 2 * fade_samples:
            # Fade in
            fade_in = np.linspace(0.0, 1.0, fade_samples)
            audio_float[:fade_samples] *= fade_in
            
            # Fade out
            fade_out = np.linspace(1.0, 0.0, fade_samples)
            audio_float[-fade_samples:] *= fade_out
        
        return audio_float.astype(np.int16)
    
    def _audio_playback_worker(self):
        """Thread worker pour la lecture audio en streaming."""
        logger.info("Démarrage du worker de lecture audio en streaming")
        
        # Configuration du streaming audio
        CHUNK_SIZE = 4096  # Taille de chunk à lire du buffer
        MIN_BUFFER = 8192  # Taille minimale de buffer avant de commencer la lecture
        
        # Variables d'état
        stream = None
        is_active = False
        
        try:
            while not self.stop_requested:
                # Attendre que des données soient disponibles
                if self.pcm_buffer.get_available() < MIN_BUFFER:
                    if not self.pcm_buffer.wait_for_data(0.1):
                        # Pas de données disponibles, continuer à vérifier
                        continue
                
                # Créer le flux audio si nécessaire
                if stream is None:
                    try:
                        stream = sd.OutputStream(
                            samplerate=self.sample_rate,
                            channels=1,
                            dtype='int16',
                            callback=self._audio_callback,
                            finished_callback=self._stream_finished
                        )
                        stream.start()
                        is_active = True
                        logger.info("Démarrage du streaming audio")
                    except Exception as e:
                        logger.error(f"Erreur lors de la création du flux audio: {e}")
                        time.sleep(1)  # Attendre avant de réessayer
                        continue
                
                # Continuer la lecture tant que le flux est actif
                if is_active:
                    time.sleep(0.1)
                else:
                    # Si le flux est terminé mais qu'il y a encore des données
                    if self.pcm_buffer.get_available() > 0:
                        try:
                            stream = sd.OutputStream(
                                samplerate=self.sample_rate,
                                channels=1,
                                dtype='int16',
                                callback=self._audio_callback,
                                finished_callback=self._stream_finished
                            )
                            stream.start()
                            is_active = True
                            logger.info("Redémarrage du streaming audio")
                        except Exception as e:
                            logger.error(f"Erreur lors du redémarrage du flux audio: {e}")
                            time.sleep(1)
                
                # Vérifier si nous devons arrêter la lecture
                if self.stop_requested and stream is not None:
                    stream.stop()
                    stream.close()
                    stream = None
                    is_active = False
                    self.pcm_buffer.clear()
        
        except Exception as e:
            logger.error(f"Erreur dans le worker de lecture audio: {e}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except:
                    pass
            logger.info("Arrêt du worker de lecture audio")
    
    def _audio_callback(self, outdata, frames, time, status):
        """Callback appelé par sounddevice pour récupérer les données audio."""
        if status:
            logger.warning(f"Status du callback audio: {status}")
            
        # Lire les données du buffer
        data = self.pcm_buffer.read(frames)
        
        # Si pas assez de données, compléter avec des zéros
        if len(data) < frames:
            temp = np.zeros(frames, dtype=np.int16)
            temp[:len(data)] = data
            data = temp
            
            # Si plus aucune donnée et plus aucun thread de synthèse actif
            if len(data) == 0 and len(self.synthesis_threads) == 0:
                self.is_speaking = False
                raise sd.CallbackStop
        
        # Copier les données dans le buffer de sortie
        outdata[:, 0] = data
    
    def _stream_finished(self):
        """Appelé lorsque le stream audio est terminé."""
        logger.debug("Stream audio terminé")
    
    def stop(self):
        """Arrête la synthèse vocale en cours."""
        logger.info("Arrêt de la synthèse demandé")
        self.stop_requested = True
        
        # Vider le buffer PCM
        self.pcm_buffer.clear()
        
        # Réinitialiser l'état
        with self.text_buffer_lock:
            self.text_buffer = ""
            
        # Attendre que tous les threads de synthèse soient terminés
        threads_copy = self.synthesis_threads.copy()
        for thread in threads_copy:
            if thread.is_alive():
                thread.join(timeout=1)
        
        self.is_speaking = False
    
    def cleanup(self):
        """Nettoie les ressources (à appeler lors de l'arrêt du programme)."""
        logger.info("Nettoyage des ressources TTS")
        self.stop()
        
        # Attendre que le thread audio soit terminé
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)