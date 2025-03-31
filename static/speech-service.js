// speech-service.js - Service de synthèse vocale optimisé

const TTS_SERVICE_URL = 'http://localhost:5002';
let ttsEnabled = true;
let pendingSpeech = false;
let pendingTextFragments = [];
let streamingMode = false;
let processingTimeout = null;

// Service de synthèse vocale
const speechService = {
    /**
     * Synthétise un texte en audio
     * @param {string} text - Texte à synthétiser
     * @param {boolean} isStreaming - Mode streaming ou complet
     * @returns {Promise} - Promesse résolue lorsque la requête est envoyée
     */
    speak: async function(text, isStreaming = false) {
        if (!ttsEnabled || !text) return;
        
        // En mode streaming, nous accumulons les fragments de texte
        if (isStreaming) {
            this.accumulateTextFragment(text);
            return;
        }
        
        // Mode normal (non-streaming)
        if (pendingSpeech) return;
        
        try {
            pendingSpeech = true;
            
            const response = await fetch(`${TTS_SERVICE_URL}/speak`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error(`Erreur TTS (${response.status}):`, errorText);
            }
        } catch (error) {
            console.error('Erreur TTS:', error);
        } finally {
            pendingSpeech = false;
        }
    },
    
    /**
     * Accumule les fragments de texte et les traite intelligemment
     * pour éviter les coupures au milieu des phrases
     * @param {string} textFragment - Fragment de texte à accumuler
     */
    accumulateTextFragment: function(textFragment) {
        // Ajouter ce fragment à notre liste
        pendingTextFragments.push(textFragment);
        
        // Indiquer qu'on est en mode streaming
        streamingMode = true;
        
        // Nettoyer les espaces et sauts de ligne excessifs dans les fragments
        const cleanedFragments = pendingTextFragments.map(f => 
            f.trim().replace(/\s+/g, ' ')
        );
        
        // Rejoindre tous les fragments pour avoir le texte complet accumulé
        const combinedText = cleanedFragments.join(' ').trim();
        
        // Si nous avons un minuteur en cours, l'annuler
        if (processingTimeout) {
            clearTimeout(processingTimeout);
        }
        
        // Logique pour détecter des phrases complètes dans le texte accumulé
        const sentenceEndPattern = /[.!?।।;](\s|$)/;
        
        // Trouver la dernière fin de phrase dans le texte combiné
        const lastSentenceEnd = this.findLastSentenceEnd(combinedText);
        
        if (lastSentenceEnd > 0) {
            // On a au moins une phrase complète
            const completeText = combinedText.substring(0, lastSentenceEnd + 1);
            const remainingText = combinedText.substring(lastSentenceEnd + 1).trim();
            
            // Envoyer la partie complète
            this.sendTextToSynthesize(completeText);
            
            // Garder le reste pour plus tard
            pendingTextFragments = remainingText ? [remainingText] : [];
        } else {
            // Pas de phrase complète, mais vérifier si nous avons beaucoup de texte déjà
            // ou s'il y a une pause probable (comme un saut de ligne)
            if (combinedText.length > 100 || combinedText.includes("\n")) {
                this.sendTextToSynthesize(combinedText);
                pendingTextFragments = [];
            }
        }
        
        // Définir un délai pour traiter le reste s'il y a un retard dans les prochains fragments
        processingTimeout = setTimeout(() => {
            if (pendingTextFragments.length > 0) {
                const remainingText = pendingTextFragments.join(' ').trim();
                if (remainingText) {
                    this.sendTextToSynthesize(remainingText);
                }
                pendingTextFragments = [];
            }
            streamingMode = false;
        }, 500);
    },
    
    /**
     * Trouve l'index de la dernière fin de phrase dans un texte
     * @param {string} text - Texte à analyser
     * @returns {number} - Position de la dernière fin de phrase, ou -1 si aucune trouvée
     */
    findLastSentenceEnd: function(text) {
        // Ponctuation qui indique la fin d'une phrase
        const endMarkers = ['.', '!', '?', ':', ';'];
        let lastIndex = -1;
        
        // Chercher la dernière occurrence de chaque marqueur
        for (const marker of endMarkers) {
            const idx = text.lastIndexOf(marker);
            if (idx > lastIndex) {
                // Vérifier que ce n'est pas une abréviation (ex: "Dr.")
                if (marker === '.' && idx > 0 && idx < text.length - 1) {
                    // Si la lettre avant est minuscule et la lettre après est majuscule,
                    // c'est probablement une vraie fin de phrase
                    const nextCharIsSpace = idx === text.length - 1 || /\s/.test(text[idx + 1]);
                    if (nextCharIsSpace) {
                        lastIndex = idx;
                    }
                } else {
                    lastIndex = idx;
                }
            }
        }
        
        return lastIndex;
    },
    
    /**
     * Envoie réellement le texte au service TTS
     * @param {string} text - Texte à synthétiser
     * @private
     */
    sendTextToSynthesize: async function(text) {
        if (!text || !ttsEnabled) return;
        
        try {
            // Éviter les chevauchements dans le mode streaming
            if (pendingSpeech) {
                await this.waitForPreviousSpeech(100, 2000); // Attendre max 2 secondes
            }
            
            pendingSpeech = true;
            
            const response = await fetch(`${TTS_SERVICE_URL}/speak`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (!response.ok) {
                console.error(`Erreur TTS (${response.status}):`, await response.text());
            }
        } catch (error) {
            console.error('Erreur lors de la synthèse:', error);
        } finally {
            // On ne met pas pendingSpeech à false ici, cela sera fait dans checkSpeakingStatus
            // Démarrer la vérification de l'état de la parole
            this.checkSpeakingStatus();
        }
    },
    
    /**
     * Attend que la synthèse précédente soit terminée
     * @param {number} interval - Intervalle entre les vérifications
     * @param {number} timeout - Délai maximum d'attente
     * @returns {Promise} - Promesse résolue quand la synthèse est terminée ou le délai expiré
     * @private
     */
    waitForPreviousSpeech: function(interval, timeout) {
        return new Promise((resolve) => {
            const startTime = Date.now();
            
            const checkStatus = () => {
                if (!pendingSpeech) {
                    resolve();
                    return;
                }
                
                if (Date.now() - startTime > timeout) {
                    // Délai expiré, continuer quand même
                    resolve();
                    return;
                }
                
                setTimeout(checkStatus, interval);
            };
            
            checkStatus();
        });
    },
    
    /**
     * Vérifie périodiquement si la synthèse est terminée
     * @private
     */
    checkSpeakingStatus: async function() {
        try {
            const response = await fetch(`${TTS_SERVICE_URL}/status`);
            if (response.ok) {
                const data = await response.json();
                
                if (!data.is_speaking) {
                    pendingSpeech = false;
                    return;
                }
                
                // Vérifier à nouveau après un court délai
                setTimeout(() => this.checkSpeakingStatus(), 100);
            }
        } catch (error) {
            console.error('Erreur de vérification du statut:', error);
            pendingSpeech = false;
        }
    },
    
    /**
     * Arrête la synthèse vocale en cours
     * @returns {Promise} - Promesse résolue lorsque la synthèse est arrêtée
     */
    stop: async function() {
        try {
            // Arrêter l'accumulation de texte
            pendingTextFragments = [];
            if (processingTimeout) {
                clearTimeout(processingTimeout);
                processingTimeout = null;
            }
            
            streamingMode = false;
            
            const response = await fetch(`${TTS_SERVICE_URL}/stop`, { method: 'POST' });
            pendingSpeech = false;
            return response.ok;
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de la synthèse:', error);
            pendingSpeech = false;
            return false;
        }
    },
    
    /**
     * Active/désactive la synthèse vocale
     * @returns {boolean} - Nouvel état (activé/désactivé)
     */
    toggle: function() {
        ttsEnabled = !ttsEnabled;
        if (!ttsEnabled) {
            this.stop();
        }
        return ttsEnabled;
    },
    
    /**
     * Vérifie si le service TTS est disponible
     * @returns {Promise<boolean>} - Promesse résolue avec l'état du service
     */
    checkAvailability: async function() {
        try {
            const response = await fetch(`${TTS_SERVICE_URL}/status`);
            if (response.ok) {
                const data = await response.json();
                return data.status === 'running';
            }
            return false;
        } catch (error) {
            console.error('Erreur de vérification du service TTS:', error);
            return false;
        }
    },
    
    /**
     * Réinitialise l'état du service (utile en cas de changement de contexte)
     */
    reset: function() {
        pendingTextFragments = [];
        if (processingTimeout) {
            clearTimeout(processingTimeout);
            processingTimeout = null;
        }
        streamingMode = false;
    }
};

// Fonction appelée par le bouton dans l'interface
function toggleTTS() {
    const enabled = speechService.toggle();
    
    // Mettre à jour l'interface
    const ttsBtnIcon = document.getElementById('tts-icon');
    if (enabled) {
        ttsBtnIcon.classList.remove('disabled');
        addMessage('system', 'Synthèse vocale activée');
    } else {
        ttsBtnIcon.classList.add('disabled');
        addMessage('system', 'Synthèse vocale désactivée');
        
        // Arrêter toute synthèse vocale en cours
        speechService.stop();
    }
}

// Vérifier la disponibilité du service TTS au chargement
document.addEventListener('DOMContentLoaded', async function() {
    const available = await speechService.checkAvailability();
    if (!available) {
        console.warn('Le service TTS ne semble pas disponible. La synthèse vocale pourrait ne pas fonctionner correctement.');
        const ttsBtnIcon = document.getElementById('tts-icon');
        ttsBtnIcon.classList.add('disabled');
        ttsEnabled = false;
    }
});