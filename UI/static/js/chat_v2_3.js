// OpenClaw Chat UI JavaScript v2.3
// 支持工具调用显示和流式响应

class ChatApp {
    constructor() {
        this.messagesContainer = document.getElementById('chat-messages');
        this.messageInput = document.getElementById('message-input');
        this.sendButton = document.getElementById('send-button');
        this.connectionStatus = document.getElementById('connection-status');
        this.websocket = null;
        this.isConnected = false;
        this.sessionId = null;
        this.isStreaming = false;
        this.availableTools = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.connectWebSocket();
        this.autoResizeTextarea();
        console.log('[ChatApp] 初始化完成 v2.3 (Tool-Use Loop)');
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
        
        console.log('[WebSocket] 正在连接:', wsUrl);
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('[WebSocket] 连接已建立');
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('[WebSocket] 收到消息:', data.type, data);
                this.handleMessage(data);
            };
            
            this.websocket.onclose = (event) => {
                this.isConnected = false;
                this.updateConnectionStatus(false);
                console.log('[WebSocket] 连接已断开');
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
            this.websocket.onerror = (error) => {
                console.error('[WebSocket] 错误:', error);
            };
        } catch (error) {
            console.error('[WebSocket] 连接失败:', error);
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
        switch (data.type) {
            case 'connected':
                this.isConnected = true;
                this.sessionId = data.session_id;
                this.availableTools = data.tools || [];
                this.updateConnectionStatus(true);
                console.log('[Chat] 会话已建立, 可用工具:', this.availableTools);
                break;
                
            case 'message':
                this.removeTypingIndicator();
                this.addMessage(data.content, data.role || 'assistant', data.tool_calls);
                break;
                
            case 'stream_start':
                console.log('[Stream] 开始');
                this.removeTypingIndicator();
                this.isStreaming = true;
                this.startStreamMessage();
                break;
                
            case 'stream_chunk':
                if (this.isStreaming) {
                    this.appendToStreamMessage(data.content);
                }
                break;
                
            case 'stream_end':
                console.log('[Stream] 结束');
                this.isStreaming = false;
                this.endStreamMessage();
                break;
                
            case 'tool_call':
                console.log('[Tool] 调用工具:', data.tools);
                this.showToolCallIndicator(data.tools);
                break;
                
            case 'tool_result':
                console.log('[Tool] 结果:', data.tool, data.success);
                this.updateToolCallIndicator(data.tool, data.success);
                break;
                
            case 'error':
                this.removeTypingIndicator();
                this.removeToolCallIndicator();
                this.isStreaming = false;
                this.addMessage(`错误: ${data.content}`, 'system');
                break;
                
            case 'pong':
                break;
                
            default:
                console.log('[WebSocket] 未知消息类型:', data.type);
        }
    }
    
    sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content) return;
        
        if (this.isStreaming) {
            console.log('[Chat] 正在处理中...');
            return;
        }
        
        this.addMessage(content, 'user');
        this.messageInput.value = '';
        this.autoResizeTextarea();
        
        if (this.isConnected && this.websocket) {
            console.log('[Chat] 发送消息:', content.substring(0, 50));
            
            this.websocket.send(JSON.stringify({
                type: 'message',
                content: content,
                enable_tools: true
            }));
            
            this.showTypingIndicator();
        } else {
            this.sendMessageHTTP(content);
        }
    }
    
    async sendMessageHTTP(content) {
        try {
            this.showTypingIndicator();
            
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message: content,
                    session_id: this.sessionId,
                    enable_tools: true
                })
            });
            
            const data = await response.json();
            this.removeTypingIndicator();
            
            if (data.success) {
                this.addMessage(data.response, 'assistant', data.tool_calls);
                this.sessionId = data.session_id;
            } else {
                this.addMessage(`错误: ${data.error}`, 'system');
            }
        } catch (error) {
            this.removeTypingIndicator();
            this.addMessage(`网络错误: ${error.message}`, 'system');
        }
    }
    
    addMessage(content, role, toolCalls = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // 处理代码块
        if (content.includes('```')) {
            contentDiv.innerHTML = this.formatCodeBlocks(content);
        } else {
            contentDiv.textContent = content;
        }
        
        messageDiv.appendChild(contentDiv);
        
        // 显示工具调用信息
        if (toolCalls && toolCalls.length > 0) {
            const toolsDiv = document.createElement('div');
            toolsDiv.className = 'tool-calls-info';
            toolsDiv.innerHTML = `<small>🔧 使用了工具: ${toolCalls.map(t => t.name).join(', ')}</small>`;
            messageDiv.appendChild(toolsDiv);
        }
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = this.formatTime(new Date());
        messageDiv.appendChild(timeDiv);
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    formatCodeBlocks(text) {
        return text.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code class="language-${lang || 'text'}">${this.escapeHtml(code.trim())}</code></pre>`;
        }).replace(/\n/g, '<br>');
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    showTypingIndicator() {
        if (document.getElementById('typing-indicator')) return;
        
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'message assistant';
        indicatorDiv.id = 'typing-indicator';
        indicatorDiv.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        
        this.messagesContainer.appendChild(indicatorDiv);
        this.scrollToBottom();
    }
    
    removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }
    
    showToolCallIndicator(tools) {
        this.removeTypingIndicator();
        
        const existing = document.getElementById('tool-call-indicator');
        if (existing) existing.remove();
        
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'message system tool-call-message';
        indicatorDiv.id = 'tool-call-indicator';
        
        const toolsList = tools.map(t => `
            <div class="tool-item" id="tool-${t.name}">
                <span class="tool-icon">🔧</span>
                <span class="tool-name">${t.name}</span>
                <span class="tool-status">执行中...</span>
            </div>
        `).join('');
        
        indicatorDiv.innerHTML = `
            <div class="message-content">
                <div class="tool-call-header">正在执行工具...</div>
                <div class="tool-list">${toolsList}</div>
            </div>
        `;
        
        this.messagesContainer.appendChild(indicatorDiv);
        this.scrollToBottom();
    }
    
    updateToolCallIndicator(toolName, success) {
        const toolItem = document.getElementById(`tool-${toolName}`);
        if (toolItem) {
            const statusSpan = toolItem.querySelector('.tool-status');
            if (statusSpan) {
                statusSpan.textContent = success ? '✅ 完成' : '❌ 失败';
                statusSpan.className = `tool-status ${success ? 'success' : 'error'}`;
            }
        }
    }
    
    removeToolCallIndicator() {
        const indicator = document.getElementById('tool-call-indicator');
        if (indicator) indicator.remove();
    }
    
    startStreamMessage() {
        const existing = document.getElementById('stream-message');
        if (existing) existing.remove();
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.id = 'stream-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.id = 'stream-content';
        
        const cursor = document.createElement('span');
        cursor.className = 'stream-cursor';
        cursor.textContent = '▊';
        contentDiv.appendChild(cursor);
        
        messageDiv.appendChild(contentDiv);
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    appendToStreamMessage(chunk) {
        const contentDiv = document.getElementById('stream-content');
        if (contentDiv) {
            const cursor = contentDiv.querySelector('.stream-cursor');
            if (cursor) cursor.remove();
            
            contentDiv.appendChild(document.createTextNode(chunk));
            
            const newCursor = document.createElement('span');
            newCursor.className = 'stream-cursor';
            newCursor.textContent = '▊';
            contentDiv.appendChild(newCursor);
            
            this.scrollToBottom();
        }
    }
    
    endStreamMessage() {
        const messageDiv = document.getElementById('stream-message');
        if (messageDiv) {
            messageDiv.removeAttribute('id');
            
            const contentDiv = document.getElementById('stream-content');
            if (contentDiv) {
                const cursor = contentDiv.querySelector('.stream-cursor');
                if (cursor) cursor.remove();
                contentDiv.removeAttribute('id');
                
                const timeDiv = document.createElement('div');
                timeDiv.className = 'message-time';
                timeDiv.textContent = this.formatTime(new Date());
                messageDiv.appendChild(timeDiv);
            }
        }
        
        this.removeToolCallIndicator();
    }
    
    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
    
    formatTime(date) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('[OpenClaw] Chat UI v2.3 加载中...');
    window.chatApp = new ChatApp();
});
