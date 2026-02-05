// OpenClaw Chat UI JavaScript v2.2
// 支持流式响应和完整的交互反馈

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
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.connectWebSocket();
        this.autoResizeTextarea();
        console.log('[ChatApp] 初始化完成 v2.2');
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
                console.log('[WebSocket] 连接已断开, code:', event.code);
                
                // 3秒后尝试重连
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
            this.websocket.onerror = (error) => {
                console.error('[WebSocket] 错误:', error);
                this.updateConnectionStatus(false);
            };
        } catch (error) {
            console.error('[WebSocket] 连接失败:', error);
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
        switch (data.type) {
            case 'connected':
                // 连接确认
                this.isConnected = true;
                this.sessionId = data.session_id;
                this.updateConnectionStatus(true);
                console.log('[Chat] 会话已建立:', this.sessionId);
                break;
                
            case 'message':
                // 完整消息 (非流式)
                this.removeTypingIndicator();
                this.addMessage(data.content, data.role || 'assistant');
                break;
                
            case 'stream_start':
                // 流式响应开始
                console.log('[Stream] 开始接收流式响应');
                this.removeTypingIndicator();
                this.isStreaming = true;
                this.startStreamMessage();
                break;
                
            case 'stream_chunk':
                // 流式响应片段
                if (this.isStreaming) {
                    this.appendToStreamMessage(data.content);
                }
                break;
                
            case 'stream_end':
                // 流式响应结束
                console.log('[Stream] 流式响应完成');
                this.isStreaming = false;
                this.endStreamMessage();
                break;
                
            case 'error':
                // 错误消息
                this.removeTypingIndicator();
                this.isStreaming = false;
                this.addMessage(`错误: ${data.content}`, 'system');
                console.error('[Chat] 错误:', data.content);
                break;
                
            case 'pong':
                // 心跳响应
                console.log('[WebSocket] Pong');
                break;
                
            default:
                console.log('[WebSocket] 未知消息类型:', data.type);
        }
    }
    
    sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content) return;
        
        if (this.isStreaming) {
            console.log('[Chat] 正在生成中，请稍候...');
            return;
        }
        
        // 添加用户消息到界面
        this.addMessage(content, 'user');
        
        // 清空输入框
        this.messageInput.value = '';
        this.autoResizeTextarea();
        
        // 发送到服务器
        if (this.isConnected && this.websocket) {
            console.log('[Chat] 发送消息:', content.substring(0, 50) + '...');
            
            this.websocket.send(JSON.stringify({
                type: 'message',
                content: content
            }));
            
            // 显示等待指示器
            this.showTypingIndicator();
        } else {
            // WebSocket 未连接时使用 HTTP
            console.log('[Chat] WebSocket 未连接，使用 HTTP');
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
                body: JSON.stringify({ 
                    message: content,
                    session_id: this.sessionId
                })
            });
            
            const data = await response.json();
            
            this.removeTypingIndicator();
            
            if (data.success) {
                this.addMessage(data.response, 'assistant');
                if (data.session_id) {
                    this.sessionId = data.session_id;
                }
            } else {
                this.addMessage(`错误: ${data.error}`, 'system');
            }
        } catch (error) {
            this.removeTypingIndicator();
            this.addMessage(`网络错误: ${error.message}`, 'system');
            console.error('[HTTP] 请求失败:', error);
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
        const existingIndicator = document.getElementById('typing-indicator');
        if (existingIndicator) return;
        
        const indicatorDiv = document.createElement('div');
        indicatorDiv.className = 'message assistant';
        indicatorDiv.id = 'typing-indicator';
        indicatorDiv.innerHTML = `
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        
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
        // 移除已有的流式消息容器
        const existingStream = document.getElementById('stream-message');
        if (existingStream) {
            existingStream.remove();
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.id = 'stream-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.id = 'stream-content';
        
        // 添加光标动画
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
            // 移除光标，添加内容，再加回光标
            const cursor = contentDiv.querySelector('.stream-cursor');
            if (cursor) cursor.remove();
            
            // 添加文本
            const textNode = document.createTextNode(chunk);
            contentDiv.appendChild(textNode);
            
            // 重新添加光标
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
                // 移除光标
                const cursor = contentDiv.querySelector('.stream-cursor');
                if (cursor) cursor.remove();
                
                contentDiv.removeAttribute('id');
                
                // 添加时间戳
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

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    console.log('[OpenClaw] Chat UI v2.2 加载中...');
    window.chatApp = new ChatApp();
});
