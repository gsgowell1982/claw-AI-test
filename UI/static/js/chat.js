// OpenClaw Chat UI JavaScript

class ChatApp {
    constructor() {
        this.messagesContainer = document.getElementById('chat-messages');
        this.messageInput = document.getElementById('message-input');
        this.sendButton = document.getElementById('send-button');
        this.connectionStatus = document.getElementById('connection-status');
        this.websocket = null;
        this.isConnected = false;
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.connectWebSocket();
        this.autoResizeTextarea();
    }
    
    bindEvents() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        this.messageInput.addEventListener('input', () => {
            this.autoResizeTextarea();
        });
    }
    
    autoResizeTextarea() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 150) + 'px';
    }
    
    connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/chat`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                this.isConnected = true;
                this.updateConnectionStatus(true);
                console.log('WebSocket connected');
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };
            
            this.websocket.onclose = () => {
                this.isConnected = false;
                this.updateConnectionStatus(false);
                console.log('WebSocket disconnected');
                // Attempt to reconnect after 3 seconds
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus(false);
            };
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.updateConnectionStatus(false);
        }
    }
    
    updateConnectionStatus(connected) {
        if (connected) {
            this.connectionStatus.textContent = '已连接';
            this.connectionStatus.classList.add('connected');
            this.connectionStatus.classList.remove('disconnected');
        } else {
            this.connectionStatus.textContent = '未连接';
            this.connectionStatus.classList.add('disconnected');
            this.connectionStatus.classList.remove('connected');
        }
    }
    
    handleMessage(data) {
        // Remove typing indicator if present
        this.removeTypingIndicator();
        
        switch (data.type) {
            case 'message':
                this.addMessage(data.content, data.role || 'assistant');
                break;
            case 'stream_start':
                this.startStreamMessage();
                break;
            case 'stream_chunk':
                this.appendToStreamMessage(data.content);
                break;
            case 'stream_end':
                this.endStreamMessage();
                break;
            case 'error':
                this.addMessage(`错误: ${data.content}`, 'system');
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content) return;
        
        // Add user message to chat
        this.addMessage(content, 'user');
        
        // Clear input
        this.messageInput.value = '';
        this.autoResizeTextarea();
        
        // Send to server
        if (this.isConnected && this.websocket) {
            this.websocket.send(JSON.stringify({
                type: 'message',
                content: content
            }));
            
            // Show typing indicator
            this.showTypingIndicator();
        } else {
            // Fallback to HTTP if WebSocket not connected
            this.sendMessageHTTP(content);
        }
    }
    
    async sendMessageHTTP(content) {
        try {
            this.showTypingIndicator();
            
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: content })
            });
            
            const data = await response.json();
            
            this.removeTypingIndicator();
            
            if (data.success) {
                this.addMessage(data.response, 'assistant');
            } else {
                this.addMessage(`错误: ${data.error}`, 'system');
            }
        } catch (error) {
            this.removeTypingIndicator();
            this.addMessage(`网络错误: ${error.message}`, 'system');
        }
    }
    
    addMessage(content, role) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = this.formatTime(new Date());
        
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeDiv);
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    showTypingIndicator() {
        const existingIndicator = this.messagesContainer.querySelector('.typing-indicator');
        if (existingIndicator) return;
        
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'message assistant';
        indicatorDiv.innerHTML = `
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        indicatorDiv.id = 'typing-indicator';
        
        this.messagesContainer.appendChild(indicatorDiv);
        this.scrollToBottom();
    }
    
    removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }
    
    startStreamMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.id = 'stream-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.id = 'stream-content';
        
        messageDiv.appendChild(contentDiv);
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    appendToStreamMessage(chunk) {
        const contentDiv = document.getElementById('stream-content');
        if (contentDiv) {
            contentDiv.textContent += chunk;
            this.scrollToBottom();
        }
    }
    
    endStreamMessage() {
        const messageDiv = document.getElementById('stream-message');
        if (messageDiv) {
            messageDiv.removeAttribute('id');
            
            const contentDiv = document.getElementById('stream-content');
            if (contentDiv) {
                contentDiv.removeAttribute('id');
                
                const timeDiv = document.createElement('div');
                timeDiv.className = 'message-time';
                timeDiv.textContent = this.formatTime(new Date());
                messageDiv.appendChild(timeDiv);
            }
        }
    }
    
    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
    
    formatTime(date) {
        return date.toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

// Initialize chat app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
