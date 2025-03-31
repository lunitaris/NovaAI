function toggleTTS() {
    ttsEnabled = !ttsEnabled;
    
    // Mettre à jour l'interface
    if (ttsBtnIcon) {
        if (ttsEnabled) {
            ttsBtnIcon.classList.remove('disabled');
            addMessage('system', 'Synthèse vocale activée');
        } else {
            ttsBtnIcon.classList.add('disabled');
            addMessage('system', 'Synthèse vocale désactivée');
            
            // Arrêter la synthèse vocale en cours
            fetch('/stop-tts', { method: 'POST' }).catch(console.error);
        }
    }
}

// Événements pour l'interface de saisie
function setupInputEvents() {
    // Événements pour le champ de saisie
    if (messageInput) {
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
    }
}

// Initialisation de l'application
function init() {
    // Charger les modèles disponibles
    loadModels();
    
    // Définir l'état initial de l'interface
    setAIState('idle');
    
    // Configurer les événements d'entrée
    setupInputEvents();
    
    // Boutons d'interface
    if (micButton) {
        micButton.addEventListener('click', toggleRecording);
    }
    
    if (micButtonStream) {
        micButtonStream.addEventListener('click', toggleRecordingStream);
    }
    
    if (modeToggleButton) {
        modeToggleButton.addEventListener('click', toggleConversationMode);
    }
    
    // Bouton TTS
    const ttsButton = document.getElementById('tts-button');
    if (ttsButton) {
        ttsButton.addEventListener('click', toggleTTS);
    }
    
    // Message de bienvenue
    addMessage('system', 'Assistant IA Local initialisé. Deux modes disponibles: Micro bleu (standard) et Micro violet (streaming). Utilisez Shift+Enter pour tester le streaming en mode texte.');
}

// Démarrer l'application lorsque le DOM est chargé
document.addEventListener('DOMContentLoaded', init);// script.js - Script principal de l'interface utilisateur

// Éléments DOM
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const modelSelect = document.getElementById('model-select');
const aiCircle = document.getElementById('ai-circle');
const micButton = document.getElementById('mic-button');
const micButtonStream = document.getElementById('mic-button-stream');
const ttsBtnIcon = document.getElementById('tts-icon');
const modeToggleButton = document.getElementById('mode-switch-button');

// État de l'application
let conversationHistory = [];
let currentState = 'idle';
let isRecording = false;
let isRecordingStream = false;
let ttsEnabled = true;

// Fonctions d'interface utilisateur
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

function loadModels() {
    fetch('/models')
        .then(response => response.json())
        .then(data => {
            // Effacer les options existantes
            modelSelect.innerHTML = '';
            
            // Ajouter les modèles disponibles
            if (data.models && data.models.length > 0) {
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model.name;
                    option.textContent = model.name;
                    modelSelect.appendChild(option);
                });
                
                // Sélectionner llama3 par défaut si disponible
                const llama3Option = Array.from(modelSelect.options).find(option => option.value.includes('llama3'));
                if (llama3Option) llama3Option.selected = true;
            } else {
                // Ajouter des modèles par défaut en cas d'erreur
                ['llama3:latest', 'mistral:latest', 'phi:latest', 'zephyr:latest'].forEach(modelName => {
                    const option = document.createElement('option');
                    option.value = modelName;
                    option.textContent = modelName;
                    modelSelect.appendChild(option);
                });
                
                // Sélectionner llama3 par défaut
                const defaultOption = Array.from(modelSelect.options).find(option => option.value.includes('llama3'));
                if (defaultOption) defaultOption.selected = true;
            }
        })
        .catch(error => {
            console.error('Erreur lors du chargement des modèles:', error);
            
            // Ajouter des modèles par défaut en cas d'erreur
            ['llama3:latest', 'mistral:latest', 'phi:latest', 'zephyr:latest'].forEach(modelName => {
                const option = document.createElement('option');
                option.value = modelName;
                option.textContent = modelName;
                modelSelect.appendChild(option);
            });
            
            // Sélectionner llama3 par défaut
            const defaultOption = Array.from(modelSelect.options).find(option => option.value.includes('llama3'));
            if (defaultOption) defaultOption.selected = true;
        });
}

function addMessage(role, message) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}-message`;
    messageElement.innerText = message;
    chatContainer.appendChild(messageElement);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return messageElement;
}

// Fonctions de traitement des messages
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

async function processChatMessageStreaming(message) {
    try {
        setAIState('thinking');

        const messageElement = document.createElement('div');
        messageElement.className = 'message assistant-message';
        chatContainer.appendChild(messageElement);
        chatContainer.scrollTop = chatContainer.scrollHeight;

        const response = await fetch('/chat-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message,
                history: conversationHistory,
                model: modelSelect.value
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        setAIState('responding');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let responseText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const rawData = line.slice(6);
                    console.log("🔹 RAW SSE DATA:", rawData); // ✅ Ajouté

                    try {
                        const data = JSON.parse(rawData);

                        if (data.chunk) {
                            responseText += data.chunk;
                            messageElement.innerText = responseText;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        } 
                        else if (data.done) {
                            conversationHistory = data.history;
                            setTimeout(() => {
                                if (currentState === 'responding') {
                                    setAIState('idle');
                                }
                            }, 2000);
                        } 
                        else if (data.error) {
                            console.error('Erreur SSE:', data.error);
                            messageElement.innerText = 'Erreur de communication avec l\'assistant';
                            setAIState('idle');
                        }

                    } catch (e) {
                        console.error('❌ Erreur JSON.parse:', e, rawData);
                        messageElement.innerText = 'Erreur de parsing JSON depuis le serveur';
                        setAIState('idle');
                    }
                }
            }
        }
    } catch (error) {
        console.error('❌ Erreur fetch/chat-stream:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}


async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    await processChatMessage(message);
}

async function sendMessageStreaming() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage('user', message);
    messageInput.value = '';
    
    await processChatMessageStreaming(message);
}

// Fonctions pour la reconnaissance vocale
async function toggleRecording() {
    if (!isRecording) {
        // Démarrer l'enregistrement
        isRecording = true;
        micButton.classList.add('recording');
        setAIState('listening');
        
        try {
            await fetch('/start-recording', { method: 'POST' });
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
            // Remplacer le message d'écoute
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Arrêter l'enregistrement
            await fetch('/stop-recording', { method: 'POST' });
            
            // Attendre un moment pour laisser le temps au traitement
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription (plusieurs tentatives)
            let transcription = "";
            for (let attempt = 0; attempt < 5; attempt++) {
                const response = await fetch('/get-transcription');
                const data = await response.json();
                transcription = data.text;
                
                if (transcription) break;
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            // Remplacer le message d'attente
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle
                addMessage('user', transcription);
                await processChatMessage(transcription);
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

async function toggleRecordingStream() {
    if (!isRecordingStream) {
        // Démarrer l'enregistrement
        isRecordingStream = true;
        micButtonStream.classList.add('recording');
        micButtonStream.classList.add('streaming');
        setAIState('listening');
        
        try {
            await fetch('/start-recording', { method: 'POST' });
            addMessage('system', 'Écoute en cours (mode streaming)... Parlez maintenant.');
        } catch (error) {
            console.error('Erreur lors du démarrage de l\'enregistrement streaming:', error);
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
            // Remplacer le message d'écoute
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            addMessage('system', 'Transcription en cours... Veuillez patienter.');
            
            // Arrêter l'enregistrement
            await fetch('/stop-recording', { method: 'POST' });
            
            // Attendre un moment pour laisser le temps au traitement
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Récupérer la transcription (plusieurs tentatives)
            let transcription = "";
            for (let attempt = 0; attempt < 5; attempt++) {
                const response = await fetch('/get-transcription');
                const data = await response.json();
                transcription = data.text;
                
                if (transcription) break;
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            // Remplacer le message d'attente
            if (chatContainer.lastChild) {
                chatContainer.removeChild(chatContainer.lastChild);
            }
            
            if (transcription) {
                // Afficher la transcription et envoyer au modèle en mode streaming
                addMessage('user', transcription);
                await processChatMessageStreaming(transcription);
            } else {
                addMessage('system', 'Aucun texte détecté. Veuillez réessayer.');
                setAIState('idle');
            }
            
            // Désactiver l'indicateur de streaming
            micButtonStream.classList.remove('streaming');
        } catch (error) {
            console.error('Erreur lors de l\'arrêt de l\'enregistrement streaming:', error);
            setAIState('idle');
            micButtonStream.classList.remove('streaming');
        }
    }
}

// Fonctions pour le mode et la synthèse vocale
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
        
        addMessage('system', 'Mode vocal activé. Cliquez sur le micro pour parler.');
    } else {
        addMessage('system', 'Mode conversation activé.');
    }
    
    // Ajuster l'état de l'IA
    setAIState(currentState);
}