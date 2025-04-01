// script.js - Version nettoyée sans bouton flottant, avec bascule par onglets uniquement

let mode = "chat";
let conversationHistory = [];
let currentState = 'idle';
let isRecording = false;

// Éléments DOM
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const modelSelect = document.getElementById('model-select');
const aiCircle = document.getElementById('ai-circle');
const micButton = document.getElementById('mic-button');

function setAIState(state) {
    aiCircle.classList.remove('idle', 'listening', 'thinking', 'responding', 'working');
    aiCircle.classList.add(state);
    currentState = state;
    if (state === 'thinking') createParticles();
    else document.querySelectorAll('.particle').forEach(p => p.remove());
}

function createParticles() {
    document.querySelectorAll('.particle').forEach(p => p.remove());
    for (let i = 0; i < 12; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = '50%';
        particle.style.top = '50%';
        particle.style.transform = 'translate(-50%, -50%)';
        const angle = i * (360 / 12);
        const distance = 40 + Math.random() * 20;
        const duration = 2 + Math.random() * 3;
        const delay = Math.random() * 0.5;
        const size = 2 + Math.random() * 2;
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.animate([
            { transform: 'translate(-50%, -50%)', opacity: 0 },
            { transform: `translate(calc(-50% + ${Math.cos(angle * Math.PI / 180) * distance}px), calc(-50% + ${Math.sin(angle * Math.PI / 180) * distance}px))`, opacity: 0.8 },
            { transform: 'translate(-50%, -50%)', opacity: 0 }
        ], {
            duration: duration * 1000,
            delay: delay * 1000,
            iterations: Infinity,
            easing: 'ease-in-out'
        });
        aiCircle.appendChild(particle);
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
                model: modelSelect.value,
                mode: mode
            })
        });

        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

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
                    try {
                        const data = JSON.parse(rawData);  
                        if (data.chunk) {
                            responseText += data.chunk;
                            messageElement.innerText = responseText;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        } else if (data.done) {
                            conversationHistory = data.history;
                            if (mode === "vocal") {
                                fetch('/speak', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ text: responseText })
                                });
                            }
                            setTimeout(() => { if (currentState === 'responding') setAIState('idle'); }, 2000);
                        } else if (data.error) {
                            console.error('Erreur SSE:', data.error);
                            messageElement.innerText = 'Erreur de communication avec l\'assistant';
                            setAIState('idle');
                        }
                    } catch (e) {
                        console.error('Erreur JSON.parse:', e, rawData);
                        messageElement.innerText = 'Erreur de parsing JSON depuis le serveur';
                        setAIState('idle');
                    }
                }
            }
        }
    } catch (error) {
        console.error('Erreur fetch/chat-stream:', error);
        addMessage('system', 'Erreur de communication avec l\'assistant');
        setAIState('idle');
    }
}

async function sendMessageStreaming() {
    const message = messageInput.value.trim();
    if (!message) return;
    addMessage('user', message);
    messageInput.value = '';
    await processChatMessageStreaming(message);
}

async function toggleRecording() {
    if (!isRecording) {
        isRecording = true;
        micButton.classList.add('recording');
        setAIState('listening');
        try {
            await fetch('/start-recording', { method: 'POST' });
            addMessage('system', 'Écoute en cours... Parlez maintenant.');
        } catch (error) {
            console.error('Erreur démarrage micro:', error);
            isRecording = false;
            micButton.classList.remove('recording');
            setAIState('idle');
        }
    } else {
        isRecording = false;
        micButton.classList.remove('recording');
        setAIState('thinking');
        try {
            if (chatContainer.lastChild) chatContainer.removeChild(chatContainer.lastChild);
            addMessage('system', 'Transcription en cours...');
            await fetch('/stop-recording', { method: 'POST' });
            await new Promise(resolve => setTimeout(resolve, 3000));

            let transcription = "";
            for (let attempt = 0; attempt < 5; attempt++) {
                const res = await fetch('/get-transcription');
                const data = await res.json();
                transcription = data.text;
                if (transcription) break;
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            if (chatContainer.lastChild) chatContainer.removeChild(chatContainer.lastChild);
            if (transcription) {
                addMessage('user', transcription);
                await processChatMessageStreaming(transcription);
            } else {
                addMessage('system', 'Aucun texte détecté.');
                setAIState('idle');
            }
        } catch (error) {
            console.error('Erreur arrêt micro:', error);
            setAIState('idle');
        }
    }
}

function setupInputEvents() {
    if (messageInput) {
        messageInput.addEventListener('focus', () => {
            if (currentState === 'idle') setAIState('working');
        });
        messageInput.addEventListener('blur', () => {
            if (currentState === 'working' && messageInput.value.trim() === '') setAIState('idle');
        });
        messageInput.addEventListener('keypress', (e) => {
            if (messageInput.value.trim().length > 0) setAIState('listening');
            if (e.key === 'Enter') {
                sendMessageStreaming();
                e.preventDefault();
            }
        });
    }
}

function loadModels() {
    fetch('/models')
        .then(response => response.json())
        .then(data => {
            modelSelect.innerHTML = '';
            const models = data.models?.length ? data.models : ['llama3:latest', 'mistral:latest', 'phi:latest', 'zephyr:latest'];
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name || model;
                option.textContent = model.name || model;
                modelSelect.appendChild(option);
            });
            const defaultOption = Array.from(modelSelect.options).find(o => o.value.includes('llama3'));
            if (defaultOption) defaultOption.selected = true;
        })
        .catch(error => console.error('Erreur chargement modèles:', error));
}

document.getElementById("tab-chat").addEventListener("click", () => {
    mode = "chat";
    document.getElementById("tab-chat").classList.add("active");
    document.getElementById("tab-vocal").classList.remove("active");
    addMessage('system', '🧠 Mode Chat activé : la synthèse vocale est désactivée.');
});

document.getElementById("tab-vocal").addEventListener("click", () => {
    mode = "vocal";
    document.getElementById("tab-vocal").classList.add("active");
    document.getElementById("tab-chat").classList.remove("active");
    addMessage('system', '🔊 Mode Appel vocal activé : Nova parlera à voix haute.');
});

document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    setAIState('idle');
    setupInputEvents();
    if (micButton) micButton.addEventListener('click', toggleRecording);
    addMessage('system', 'Assistant IA local initialisé. Cliquez sur le micro ou tapez un message.');
});
