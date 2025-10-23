/**
 * WebSocket client for real-time dashboard updates
 */

class WebSocketClient {
    constructor() {
        this.ws = null;
        this.reconnectInterval = 3000;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.handlers = {};
        this.isIntentionallyClosed = false;
        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        console.log('Connecting to WebSocket:', wsUrl);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('✅ WebSocket connected');
            this.reconnectAttempts = 0;
            this.updateStatus(true);
            this.trigger('connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('📨 Received:', data.type);
                this.handleMessage(data);
            } catch (error) {
                console.error('Error parsing message:', error);
            }
        };

        this.ws.onclose = () => {
            console.log('🔌 WebSocket disconnected');
            this.updateStatus(false);
            this.trigger('disconnected');

            // Attempt to reconnect if not intentionally closed
            if (!this.isIntentionallyClosed && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`Reconnecting in ${this.reconnectInterval}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                setTimeout(() => this.connect(), this.reconnectInterval);
            }
        };

        this.ws.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
        };
    }

    updateStatus(connected) {
        const statusEl = document.getElementById('ws-status');
        if (!statusEl) return;

        if (connected) {
            statusEl.textContent = '🟢 Connected';
            statusEl.className = 'status-connected';
        } else {
            statusEl.textContent = '🔴 Disconnected';
            statusEl.className = 'status-disconnected';
        }
    }

    handleMessage(data) {
        const type = data.type;
        if (this.handlers[type]) {
            this.handlers[type].forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in handler for ${type}:`, error);
                }
            });
        }
    }

    on(type, handler) {
        if (!this.handlers[type]) {
            this.handlers[type] = [];
        }
        this.handlers[type].push(handler);
    }

    trigger(eventName) {
        const handlers = this.handlers[eventName];
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler();
                } catch (error) {
                    console.error(`Error in ${eventName} handler:`, error);
                }
            });
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket not connected, cannot send message');
        }
    }

    close() {
        this.isIntentionallyClosed = true;
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Global WebSocket instance
const wsClient = new WebSocketClient();

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    wsClient.close();
});
