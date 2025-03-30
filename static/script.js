const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const modelSelect = document.getElementById('model-select');
const aiCircle = document.getElementById('ai-circle');
const micButton = document.getElementById('mic-button');
const micButtonStream = document.getElementById('mic-button-stream');

let conversationHistory = [];
let currentState = 'idle';
let isRecording = false;
let isRecordingStream = false;
const VOICE_SERVICE_URL = 'http://localhost:5001';

// Fonction pour gérer l'état de la visualisation
function setAIState(state) {
    // Supprimer toutes les classes d'état
    aiCircle.classList.remove('idle', 'listening', 'thinking', 'responding', 'working');
    
    // Ajouter la nouvelle classe d'état
    aiCircle.classList.add(state);
    currentState = state;
    
    // Si c'est l'état de réflexion, ajouter des particules
    if (state === 'thinking') {
        createParticles();
    } else {
        // Supprimer les particules existantes
        document.querySelectorAll('.particle').forEach(p => p.remove());
    }
}

// Créer des particules pour l'animation de réflexion
function createParticles() {
    // Supprimer les particules existantes
    document.querySelectorAll('.particle').forEach(p => p.remove());
    
    // Créer de nouvelles particules
    for(let i = 0; i < 12; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Position de départ au centre
        particle.style.left = '50%';
        particle.style.top = '50%';
        particle.style.transform = 'translate(-50%, -50%)';
        
        // Animation dynamique pour chaque particule
        const angle = i * (360 / 12);
        const distance = 40 + Math.random() * 20;
        const duration = 2 + Math.random() * 3;
        const delay = Math.random() * 0.5;
        const size = 2 + Math.random() * 2;
        
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        
        particle.animate([
            { 
                transform: 'translate(-50%, -50%)',
                opacity: 0
            },
            { 
                transform: `translate(calc(-50% + ${Math.cos(angle * Math.PI / 180) * distance}px), calc(-50% + ${Math.sin(angle * Math.PI / 180) * distance}px))`,
                opacity: 0.8
            },
            { 
                transform: 'translate(-50%, -50%)',
                opacity: 0
            }
        ], {
            duration: duration * 1000,
            delay: delay * 1000,
            iterations: Infinity,
            easing: 'ease-in-out'
        });
        
        aiCircle.appendChild(particle);
    }
}

// Charger les modèles disponibles
async function loadModels() {
    try {
        const response = await fetch('/models');
        const data = await response.json();
        
        // Effacer les options existantes
        modelSelect.innerHTML = '';
        
        // Ajouter les modèles
        data.models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.name;
            option.textContent = model.name;
            modelSelect.appendChild(option);
        });
        
        // Sélectionner llama3 par défaut si disponible
        const llama3Option = Array.from(modelSelect.options).find(option => option.value.includes('llama3'));
        if (llama3Option) llama3Option.selected = true;
        
    } catch (error) {
        console.error('Erreur lors du chargement des modèles:', error);
        
        // Ajouter manuellement quelques modèles en cas d'erreur
        modelSelect.innerHTML = '';
        
        const models = [
            "llama3:latest",
            "mistral:latest",
            "phi:latest",
            "zephyr:latest"
        ];
        
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelSelect.appendChild(option);
        });
        
        // Sélectionner llama3 par défaut
        const llama3Option = Array.from(modelSelect.options).find(
            option => option.value.includes('llama3')
        );
        if (llama3Option) llama3Option.selected = true;
    }
}

function addMessage(role, message) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}-message`;
    messageElement.innerText = message;
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return messageElement;
}

// Fonction pour traiter un message de chat (texte ou vocal) - Mode classique
async function processChatMessage(message) {
    try {
        setAIState('thinking');
        
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });

        const data = await response.json();
        
        // Mettre à jour l'historique
        conversationHistory = data.history;
        
        // Changer l'état à "réponse"
        setAIState('responding');
        
        // Afficher la réponse
        addMessage('assistant', data.response);
        
        // Revenir à l'état d'attente après un délai
        setTimeout(() => {
            if (currentState === 'responding') {
                setAIState('idle');
            }
        }, 2000);
        
    } catch (error) {
        console.error('Erreur:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

// Fonction pour traiter un message de chat en streaming
async function processChatMessageStreaming(message) {
    try {
        // Changer l'état à "réflexion"
        setAIState('thinking');
        
        // Créer un élément de message pour la réponse de l'assistant
        const messageElement = document.createElement('div');
        messageElement.className = 'message assistant-message';
        chatContainer.appendChild(messageElement);
        
        // Faire défiler vers le bas pour voir la réponse
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        // Envoyer la requête et obtenir la réponse en streaming
        const response = await fetch('/chat-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });
        
        // Vérifier si la réponse est OK
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        // Changer l'état à "réponse" dès qu'on commence à recevoir des données
        setAIState('responding');
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let responseText = "";
        
        // Lire la réponse en streaming
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            // Décoder le texte reçu
            const chunk = decoder.decode(value);
            
            // Traiter chaque ligne du chunk
            const lines = chunk.split('\n\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        // Si c'est un morceau de texte
                        if (data.chunk) {
                            responseText += data.chunk;
                            messageElement.innerText = responseText;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        } 
                        // Si c'est la fin du streaming
                        else if (data.done) {
                            // Mettre à jour l'historique de conversation
                            conversationHistory = data.history;
                            
                            // Revenir à l'état d'attente après un délai
                            setTimeout(() => {
                                if (currentState === 'responding') {
                                    setAIState('idle');
                                }
                            }, 2000);
                        }
                        // Si c'est une erreur
                        else if (data.error) {
                            console.error('Erreur:', data.error);
                            messageElement.innerText = 'Erreur de communication avec l\'assistant';
                            setAIState('idle');
                        }
                    } catch (e) {
                        console.error('Erreur de parsing:', e, line);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Erreur:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    // Mode par défaut (non-streaming)
    await processChatMessage(message);
}

async function sendMessageStreaming() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    // Mode streaming
    await processChatMessageStreaming(message);
}

// Gestion de l'enregistrement vocal avec correction pour le timing - Mode classique
async function toggleRecording() {
    if (!isRecording) {
        // Démarrer l'enregistrement
        isRecording = true;
        micButton.classList.add('recording');
        setAIState('listening');
        
        try {
            await fetch(`${VOICE_SERVICE_URL}/start-recording`, {
                method: 'POST'
            });
            
            // Ajouter un message pour indiquer que l'assistant écoute
            addMessage('system', 'Écoute en cours... Parlez maintenant.');
        } catch (error) {
            console.error('Erreur lors du démarrage de l\'enregistrement:', error);
            isRecording = false;
            micButton.classList.remove('recording');
            setAIState('idle');
        }
    } else {
        // Arrêter l'enregistrement
        isRecording = false;
        micButton.classList.remove('recording');
        setAIState('thinking');
        
        try {
            // Informer l'utilisateur de l'attente
            chatContainer.removeChild(chatContainer.lastChild);
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Envoyer la requête d'arrêt
            await fetch(`${VOICE_SERVICE_URL}/stop-recording`, {
                method: 'POST'
            });
            
            // Attendre 3 secondes pour laisser le temps à whisper de traiter l'audio
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription avec plusieurs tentatives
            let attempts = 0;
            let maxAttempts = 5;
            let transcription = "";
            
            while (attempts < maxAttempts && !transcription) {
                const response = await fetch(`${VOICE_SERVICE_URL}/get-transcription`);
                const data = await response.json();
                transcription = data.text;
                
                if (!transcription) {
                    // Attendre encore un peu et réessayer
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    attempts++;
                }
            }
            
            // Remplacer le message d'attente
            chatContainer.removeChild(chatContainer.lastChild);
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle
                addMessage('user', transcription);
                processChatMessage(transcription);
            } else {
                addMessage('system', 'Aucun texte détecté. Veuillez réessayer.');
                setAIState('idle');
            }
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de l\'enregistrement:', error);
            setAIState('idle');
        }
    }
}

// Gestion de l'enregistrement vocal en mode streaming
async function toggleRecordingStream() {
    if (!isRecordingStream) {
        // Démarrer l'enregistrement
        isRecordingStream = true;
        micButtonStream.classList.add('recording');
        micButtonStream.classList.add('streaming');
        setAIState('listening');
        
        try {
            await fetch(`${VOICE_SERVICE_URL}/start-recording`, {
                method: 'POST'
            });
            
            // Ajouter un message pour indiquer que l'assistant écoute
            addMessage('system', 'Écoute en cours (mode streaming)... Parlez maintenant.');
        } catch (error) {
            console.error('Erreur lors du démarrage de l\'enregistrement:', error);
            isRecordingStream = false;
            micButtonStream.classList.remove('recording');
            micButtonStream.classList.remove('streaming');
            setAIState('idle');
        }
    } else {
        // Arrêter l'enregistrement
        isRecordingStream = false;
        micButtonStream.classList.remove('recording');
        setAIState('thinking');
        
        try {
            // Informer l'utilisateur de l'attente
            chatContainer.removeChild(chatContainer.lastChild);
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Envoyer la requête d'arrêt
            await fetch(`${VOICE_SERVICE_URL}/stop-recording`, {
                method: 'POST'
            });
            
            // Attendre 3 secondes pour laisser le temps à whisper de traiter l'audio
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription avec plusieurs tentatives
            let attempts = 0;
            let maxAttempts = 5;
            let transcription = "";
            
            while (attempts < maxAttempts && !transcription) {
                const response = await fetch(`${VOICE_SERVICE_URL}/get-transcription`);
                const data = await response.json();
                transcription = data.text;
                
                if (!transcription) {
                    // Attendre encore un peu et réessayer
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    attempts++;
                }
            }
            
            // Remplacer le message d'attente
            chatContainer.removeChild(chatContainer.lastChild);
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle en mode streaming
                addMessage('user', transcription);
                processChatMessageStreaming(transcription);
            } else {
                addMessage('system', 'Aucun texte détecté. Veuillez réessayer.');
                setAIState('idle');
            }
            
            // Désactiver l'indicateur de streaming
            micButtonStream.classList.remove('streaming');
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de l\'enregistrement:', error);
            setAIState('idle');
            micButtonStream.classList.remove('streaming');
        }
    }
}

// Simuler l'état "travail" lorsque l'utilisateur commence à taper
messageInput.addEventListener('focus', () => {
    if (currentState === 'idle') {
        setAIState('working');
    }
});

messageInput.addEventListener('blur', () => {
    if (currentState === 'working' && messageInput.value.trim() === '') {
        setAIState('idle');
    }
});

messageInput.addEventListener('keypress', (e) => {
    // Si l'utilisateur tape, passer en mode "écoute"
    if (messageInput.value.trim().length > 0) {
        setAIState('listening');
    }
    
    if (e.key === 'Enter') {
        // Vérifier si la touche Shift est enfoncée pour utiliser le mode streaming
        if (e.shiftKey) {
            sendMessageStreaming();
        } else {
            sendMessage();
        }
        e.preventDefault();
    }
});

// Fonction pour basculer entre les modes de conversation
function toggleConversationMode() {
    const body = document.body;
    const chatIcon = document.getElementById('chat-icon');
    const voiceIcon = document.getElementById('voice-icon');
    
    // Basculer la classe sur le body
    body.classList.toggle('voice-mode');
    
    // Mettre à jour les icônes
    chatIcon.classList.toggle('active');
    voiceIcon.classList.toggle('active');
    
    // Si on est en mode vocal, centrer le scroll du chat
    if (body.classList.contains('voice-mode')) {
        // Attendre que les animations de transition se terminent
        setTimeout(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }, 500);
        
        // Ajouter un message d'information
        addMessage('system', 'Mode vocal activé. Cliquez sur le micro pour parler.');
    } else {
        // Revenir au mode chat
        addMessage('system', 'Mode conversation activé.');
    }
    
    // Ajuster l'état de l'IA
    setAIState(currentState);
}

// Événements d'écoute
micButton.addEventListener('click', toggleRecording);
micButtonStream.addEventListener('click', toggleRecordingStream);
document.getElementById('mode-switch-button').addEventListener('click', toggleConversationMode);

// Initialisation
window.onload = function() {
    loadModels();
    setAIState('idle');
    
    // Ajouter un message d'information sur les deux modes
    addMessage('system', 'Deux modes disponibles : Micro bleu (standard) et Micro violet (streaming). Utilisez Shift+Enter pour tester le streaming en mode texte.');
};

// Dans script.js
document.addEventListener('DOMContentLoaded', function() {
    // Charger uniquement les composants essentiels
    const essentialComponents = ['visualization', 'chat-input'];
    loadComponents(essentialComponents);
    
    // Charger les composants secondaires après l'initialisation
    setTimeout(() => {
        const secondaryComponents = ['model-selector', 'voice-recognition'];
        loadComponents(secondaryComponents);
    }, 100);
});

// Fonction pour charger les composants (définie pour éviter des erreurs, même si elle n'est pas utilisée)
function loadComponents(components) {
    console.log('Chargement des composants:', components);
    // Cette fonction est appelée mais n'est pas implémentée dans l'exemple original
    // On la garde pour éviter des erreurs dans la console
}


////////////////////////////////////////////////// TEXT TO SPEECH (PIPER)   /////////////////////////////////////////////////////


// Ajouter cette variable
let ttsEnabled = true; // Par défaut, activer la synthèse vocale

// Ajouter cette fonction quelque part dans le fichier
async function speakText(text) {
    if (!ttsEnabled) return;
    
    try {
        const response = await fetch('http://localhost:5002/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        
        if (!response.ok) {
            console.error('Erreur lors de la synthèse vocale:', await response.text());
        }
    } catch (error) {
        console.error('Erreur lors de la synthèse vocale:', error);
    }
}

// Ajouter cette fonction pour le streaming TTS
async function streamText(text) {
    if (!ttsEnabled) return;
    
    try {
        const response = await fetch('http://localhost:5002/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        
        if (!response.ok) {
            console.error('Erreur lors de la synthèse vocale streaming:', await response.text());
        }
    } catch (error) {
        console.error('Erreur lors de la synthèse vocale streaming:', error);
    }
}

// Ajouter cette fonction pour arrêter la synthèse vocale
async function stopSpeaking() {
    try {
        await fetch('http://localhost:5002/stop', { method: 'POST' });
    } catch (error) {
        console.error('Erreur lors de l\'arrêt de la synthèse vocale:', error);
    }
}

// Modifier la fonction processChatMessage
async function processChatMessage(message) {
    try {
        setAIState('thinking');
        
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });

        const data = await response.json();
        
        // Mettre à jour l'historique
        conversationHistory = data.history;
        
        // Changer l'état à "réponse"
        setAIState('responding');
        
        // Afficher la réponse
        addMessage('assistant', data.response);
        
        // Synthétiser la réponse
        await speakText(data.response);
        
        // Revenir à l'état d'attente après un délai
        setTimeout(() => {
            if (currentState === 'responding') {
                setAIState('idle');
            }
        }, 2000);
        
    } catch (error) {
        console.error('Erreur:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

// Modifier la fonction processChatMessageStreaming pour parler en streaming
async function processChatMessageStreaming(message) {
    try {
        // Changer l'état à "réflexion"
        setAIState('thinking');
        
        // Créer un élément de message pour la réponse de l'assistant
        const messageElement = document.createElement('div');
        messageElement.className = 'message assistant-message';
        chatContainer.appendChild(messageElement);
        
        // Faire défiler vers le bas pour voir la réponse
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        // Envoyer la requête et obtenir la réponse en streaming
        const response = await fetch('/chat-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });
        
        // Vérifier si la réponse est OK
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        // Changer l'état à "réponse" dès qu'on commence à recevoir des données
        setAIState('responding');
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let responseText = "";
        let lastSpokenLength = 0;
        let accumulatedText = "";
        
        // Lire la réponse en streaming
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            // Décoder le texte reçu
            const chunk = decoder.decode(value);
            
            // Traiter chaque ligne du chunk
            const lines = chunk.split('\n\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        // Si c'est un morceau de texte
                        if (data.chunk) {
                            responseText += data.chunk;
                            messageElement.innerText = responseText;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                            
                            // Accumuler le texte pour la synthèse
                            accumulatedText += data.chunk;
                            
                            // Parler par phrases
                            const sentenceEndRegex = /[.!?。：；](?:\s|$)/g;
                            let match;
                            let lastIndex = 0;
                            let hasSentenceEnd = false;
                            
                            // Réinitialiser le regex
                            sentenceEndRegex.lastIndex = lastSpokenLength;
                            
                            // Rechercher des fins de phrases
                            while ((match = sentenceEndRegex.exec(accumulatedText)) !== null) {
                                hasSentenceEnd = true;
                                lastIndex = match.index + 1;
                            }
                            
                            // S'il y a une nouvelle phrase complète
                            if (hasSentenceEnd && lastIndex > lastSpokenLength) {
                                const textToSpeak = accumulatedText.substring(lastSpokenLength, lastIndex);
                                streamText(textToSpeak); // Parler la nouvelle phrase
                                lastSpokenLength = lastIndex;
                            }
                            // Si on a beaucoup de texte sans fin de phrase, parler quand même
                            else if (accumulatedText.length - lastSpokenLength > 50) {
                                const textToSpeak = accumulatedText.substring(lastSpokenLength);
                                streamText(textToSpeak);
                                lastSpokenLength = accumulatedText.length;
                            }
                        } 
                        // Si c'est la fin du streaming
                        else if (data.done) {
                            // Mettre à jour l'historique de conversation
                            conversationHistory = data.history;
                            
                            // Parler le reste du texte si nécessaire
                            if (lastSpokenLength < accumulatedText.length) {
                                const remainingText = accumulatedText.substring(lastSpokenLength);
                                streamText(remainingText);
                            }
                            
                            // Revenir à l'état d'attente après un délai
                            setTimeout(() => {
                                if (currentState === 'responding') {
                                    setAIState('idle');
                                }
                            }, 2000);
                        }
                        // Si c'est une erreur
                        else if (data.error) {
                            console.error('Erreur:', data.error);
                            messageElement.innerText = 'Erreur de communication avec l\'assistant';
                            setAIState('idle');
                        }
                    } catch (e) {
                        console.error('Erreur de parsing:', e, line);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Erreur:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

// Ajouter un bouton pour activer/désactiver la synthèse vocale
function toggleTTS() {
    ttsEnabled = !ttsEnabled;
    
    // Arrêter la synthèse en cours si on désactive
    if (!ttsEnabled) {
        stopSpeaking();
    }
    
    // Mettre à jour le bouton
    const ttsBtnIcon = document.getElementById('tts-icon');
    if (ttsEnabled) {
        ttsBtnIcon.classList.remove('disabled');
        addMessage('system', 'Synthèse vocale activée');
    } else {
        ttsBtnIcon.classList.add('disabled');
        addMessage('system', 'Synthèse vocale désactivée');
    }
}