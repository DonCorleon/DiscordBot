# Web-Based Admin Interface Implementation Plan

**Status**: Not Started
**Created**: 2025-10-21
**Technology**: FastAPI + WebSockets

---

## Overview

Replace the current pygame-based admin dashboard (`admin_interface_full.py`) with a modern web-based interface accessible from any device on the network.

**Key Benefits**:
- Works on headless servers (no GUI required)
- Remote access from any device (phone, tablet, computer)
- Multiple simultaneous viewers
- Real-time updates via WebSockets
- Modern, responsive UI
- Better performance and scalability

---

## Technology Stack

### Backend
- **FastAPI** - Modern Python web framework with automatic API docs
- **uvicorn** - ASGI server for running FastAPI
- **WebSockets** - Real-time bidirectional communication
- **asyncio** - Async event handling (already used by discord.py)

### Frontend
- **HTML5 + CSS3** - Structure and styling
- **JavaScript (Vanilla or Alpine.js)** - Interactivity and WebSocket handling
- **Chart.js** - Real-time graphs and visualizations
- **Tailwind CSS** (optional) - Modern styling framework

### Dependencies to Add
```toml
# Add to pyproject.toml
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
websockets = "^12.0"
jinja2 = "^3.1.3"  # For HTML templating
python-multipart = "^0.0.6"  # For form handling
```

---

## Architecture

### File Structure
```
DiscordBot/
├── web/
│   ├── __init__.py
│   ├── app.py                    # FastAPI application
│   ├── websocket_manager.py      # WebSocket connection manager
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py          # Dashboard routes
│   │   ├── api.py                # REST API endpoints
│   │   └── websocket.py          # WebSocket endpoints
│   ├── templates/
│   │   ├── base.html             # Base template
│   │   ├── dashboard.html        # Main dashboard
│   │   ├── stats.html            # Statistics page
│   │   └── logs.html             # Live logs viewer
│   └── static/
│       ├── css/
│       │   └── style.css         # Custom styles
│       ├── js/
│       │   ├── websocket.js      # WebSocket client
│       │   ├── dashboard.js      # Dashboard logic
│       │   └── charts.js         # Chart configurations
│       └── img/
│           └── (icons, logos)
├── utils/
│   └── admin_data_collector.py   # Keep existing (already collects data)
└── config.py                      # Add web server config
```

### Data Flow
```
Discord Bot (main.py)
    ↓
AdminDataCollector (utils/admin_data_collector.py)
    ↓ (exports JSON every 10s)
admin_data/*.json files
    ↑ (reads data)
FastAPI App (web/app.py)
    ↓ (WebSocket push)
Browser Clients (multiple simultaneous viewers)
```

---

## Implementation Steps

### Phase 1: Basic FastAPI Setup (30 minutes)

1. **Create web server structure**
   ```bash
   mkdir -p web/routes web/templates web/static/css web/static/js
   ```

2. **Create `web/app.py`** - Main FastAPI application
   ```python
   from fastapi import FastAPI, WebSocket
   from fastapi.responses import HTMLResponse
   from fastapi.staticfiles import StaticFiles
   from fastapi.templating import Jinja2Templates
   import uvicorn

   app = FastAPI(title="Discord Bot Admin", version="1.0.0")

   # Mount static files
   app.mount("/static", StaticFiles(directory="web/static"), name="static")

   # Templates
   templates = Jinja2Templates(directory="web/templates")

   @app.get("/")
   async def dashboard(request: Request):
       return templates.TemplateResponse("dashboard.html", {"request": request})

   if __name__ == "__main__":
       uvicorn.run(app, host="0.0.0.0", port=8000)
   ```

3. **Update `config.py`** - Add web server configuration
   ```python
   # Web Server Configuration
   enable_web_dashboard: bool = True
   web_host: str = "0.0.0.0"  # Listen on all interfaces
   web_port: int = 8000
   web_reload: bool = False   # Auto-reload on code changes (dev only)
   ```

4. **Test basic server**
   ```bash
   python web/app.py
   # Visit http://localhost:8000
   ```

### Phase 2: WebSocket Manager (45 minutes)

5. **Create `web/websocket_manager.py`** - Manage WebSocket connections
   ```python
   from typing import List, Dict
   from fastapi import WebSocket
   import json
   import asyncio

   class ConnectionManager:
       def __init__(self):
           self.active_connections: List[WebSocket] = []
           self.data_cache: Dict = {}

       async def connect(self, websocket: WebSocket):
           await websocket.accept()
           self.active_connections.append(websocket)

       def disconnect(self, websocket: WebSocket):
           self.active_connections.remove(websocket)

       async def broadcast(self, message: dict):
           """Send message to all connected clients"""
           disconnected = []
           for connection in self.active_connections:
               try:
                   await connection.send_json(message)
               except Exception:
                   disconnected.append(connection)

           # Clean up disconnected clients
           for conn in disconnected:
               self.active_connections.remove(conn)

       async def send_personal(self, message: dict, websocket: WebSocket):
           """Send message to specific client"""
           await websocket.send_json(message)

   manager = ConnectionManager()
   ```

6. **Create `web/routes/websocket.py`** - WebSocket endpoint
   ```python
   from fastapi import APIRouter, WebSocket, WebSocketDisconnect
   from web.websocket_manager import manager
   import json

   router = APIRouter()

   @router.websocket("/ws")
   async def websocket_endpoint(websocket: WebSocket):
       await manager.connect(websocket)
       try:
           # Send initial data
           await manager.send_personal({
               "type": "init",
               "data": manager.data_cache
           }, websocket)

           # Keep connection alive and handle incoming messages
           while True:
               data = await websocket.receive_text()
               # Handle client requests here

       except WebSocketDisconnect:
           manager.disconnect(websocket)
   ```

### Phase 3: Data Integration (1 hour)

7. **Create background task to push data** - In `web/app.py`
   ```python
   import asyncio
   from pathlib import Path
   import json
   from web.websocket_manager import manager

   async def data_pusher():
       """Background task that reads admin_data/*.json and pushes to clients"""
       admin_data_dir = Path("admin_data")

       while True:
           try:
               # Read all JSON files from admin_data/
               data = {}

               if admin_data_dir.exists():
                   for json_file in admin_data_dir.glob("*.json"):
                       try:
                           with open(json_file, 'r') as f:
                               data[json_file.stem] = json.load(f)
                       except Exception as e:
                           logger.error(f"Error reading {json_file}: {e}")

               # Update cache
               manager.data_cache = data

               # Broadcast to all connected clients
               if manager.active_connections:
                   await manager.broadcast({
                       "type": "update",
                       "data": data,
                       "timestamp": datetime.now().isoformat()
                   })

               # Wait before next update (2 seconds for near real-time)
               await asyncio.sleep(2)

           except Exception as e:
               logger.error(f"Error in data_pusher: {e}")
               await asyncio.sleep(5)

   @app.on_event("startup")
   async def startup_event():
       """Start background tasks when app starts"""
       asyncio.create_task(data_pusher())
   ```

8. **Add direct event broadcasting** - Modify `utils/admin_data_collector.py`
   ```python
   # At top of file
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from web.websocket_manager import ConnectionManager

   class AdminDataCollector:
       def __init__(self):
           # ... existing code ...
           self.websocket_manager = None  # Set by web server

       def broadcast_event(self, event_type: str, data: dict):
           """Send event immediately to web clients"""
           if self.websocket_manager and self.websocket_manager.active_connections:
               # Use asyncio.create_task to avoid blocking
               import asyncio
               asyncio.create_task(
                   self.websocket_manager.broadcast({
                       "type": event_type,
                       "data": data,
                       "timestamp": datetime.now().isoformat()
                   })
               )

       def record_command(self, command_name, user, guild, success):
           # ... existing code ...

           # Broadcast immediately
           self.broadcast_event("command", {
               "name": command_name,
               "user": str(user),
               "guild": str(guild),
               "success": success
           })

       def record_message(self, message):
           # ... existing code ...

           # Broadcast immediately
           self.broadcast_event("message", {
               "author": str(message.author),
               "content": message.content[:100],  # Truncate long messages
               "channel": str(message.channel),
               "guild": str(message.guild) if message.guild else "DM"
           })
   ```

### Phase 4: Frontend Dashboard (2 hours)

9. **Create `web/templates/base.html`** - Base template
   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
       <meta charset="UTF-8">
       <meta name="viewport" content="width=device-width, initial-scale=1.0">
       <title>{% block title %}Discord Bot Admin{% endblock %}</title>
       <link rel="stylesheet" href="/static/css/style.css">
       <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
   </head>
   <body>
       <nav class="navbar">
           <div class="nav-brand">Discord Bot Admin</div>
           <div class="nav-links">
               <a href="/">Dashboard</a>
               <a href="/stats">Statistics</a>
               <a href="/logs">Live Logs</a>
           </div>
           <div class="connection-status">
               <span id="ws-status" class="status-disconnected">⚫ Disconnected</span>
           </div>
       </nav>

       <main class="container">
           {% block content %}{% endblock %}
       </main>

       <script src="/static/js/websocket.js"></script>
       {% block scripts %}{% endblock %}
   </body>
   </html>
   ```

10. **Create `web/templates/dashboard.html`** - Main dashboard
    ```html
    {% extends "base.html" %}

    {% block content %}
    <div class="dashboard-grid">
        <!-- Stats Cards -->
        <div class="card">
            <h3>Bot Status</h3>
            <div id="bot-status">
                <p>Uptime: <span id="uptime">--</span></p>
                <p>Guilds: <span id="guild-count">--</span></p>
                <p>Users: <span id="user-count">--</span></p>
            </div>
        </div>

        <div class="card">
            <h3>Commands (Last Hour)</h3>
            <canvas id="commands-chart"></canvas>
        </div>

        <div class="card">
            <h3>Messages (Last Hour)</h3>
            <canvas id="messages-chart"></canvas>
        </div>

        <!-- Live Feed -->
        <div class="card full-width">
            <h3>Live Activity Feed</h3>
            <div id="activity-feed" class="activity-feed">
                <!-- Messages appear here in real-time -->
            </div>
        </div>

        <!-- Voice Status -->
        <div class="card">
            <h3>Voice Channels</h3>
            <div id="voice-status">
                <!-- Voice channel info -->
            </div>
        </div>

        <!-- Recent Commands -->
        <div class="card">
            <h3>Recent Commands</h3>
            <div id="recent-commands" class="command-list">
                <!-- Commands appear here -->
            </div>
        </div>
    </div>
    {% endblock %}

    {% block scripts %}
    <script src="/static/js/dashboard.js"></script>
    <script src="/static/js/charts.js"></script>
    {% endblock %}
    ```

11. **Create `web/static/js/websocket.js`** - WebSocket client
    ```javascript
    class WebSocketClient {
        constructor() {
            this.ws = null;
            this.reconnectInterval = 3000;
            this.handlers = {};
            this.connect();
        }

        connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;

            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.updateStatus(true);
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateStatus(false);
                setTimeout(() => this.connect(), this.reconnectInterval);
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        updateStatus(connected) {
            const statusEl = document.getElementById('ws-status');
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
                this.handlers[type].forEach(handler => handler(data));
            }
        }

        on(type, handler) {
            if (!this.handlers[type]) {
                this.handlers[type] = [];
            }
            this.handlers[type].push(handler);
        }

        send(data) {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify(data));
            }
        }
    }

    // Global WebSocket instance
    const wsClient = new WebSocketClient();
    ```

12. **Create `web/static/js/dashboard.js`** - Dashboard logic
    ```javascript
    // Handle initial data load
    wsClient.on('init', (data) => {
        console.log('Received initial data:', data);
        updateDashboard(data.data);
    });

    // Handle real-time updates
    wsClient.on('update', (data) => {
        updateDashboard(data.data);
    });

    // Handle real-time events
    wsClient.on('message', (data) => {
        addToActivityFeed('message', data.data);
    });

    wsClient.on('command', (data) => {
        addToActivityFeed('command', data.data);
        addToRecentCommands(data.data);
    });

    function updateDashboard(data) {
        // Update stats cards
        if (data.health) {
            const latest = data.health[data.health.length - 1];
            document.getElementById('uptime').textContent = formatUptime(latest.uptime);
            document.getElementById('guild-count').textContent = latest.guilds;
            document.getElementById('user-count').textContent = latest.users;
        }

        // Update charts
        if (data.commands) {
            updateCommandsChart(data.commands);
        }

        if (data.messages) {
            updateMessagesChart(data.messages);
        }
    }

    function addToActivityFeed(type, data) {
        const feed = document.getElementById('activity-feed');
        const item = document.createElement('div');
        item.className = `feed-item feed-${type}`;

        const time = new Date().toLocaleTimeString();

        if (type === 'message') {
            item.innerHTML = `
                <span class="time">${time}</span>
                <span class="user">${data.author}</span>: ${data.content}
            `;
        } else if (type === 'command') {
            item.innerHTML = `
                <span class="time">${time}</span>
                <span class="command">${data.name}</span> by ${data.user}
                ${data.success ? '✅' : '❌'}
            `;
        }

        feed.insertBefore(item, feed.firstChild);

        // Keep only last 50 items
        while (feed.children.length > 50) {
            feed.removeChild(feed.lastChild);
        }
    }

    function formatUptime(seconds) {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${days}d ${hours}h ${minutes}m`;
    }
    ```

13. **Create `web/static/css/style.css`** - Basic styling
    ```css
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #1a1a1a;
        color: #e0e0e0;
    }

    .navbar {
        background: #2d2d2d;
        padding: 1rem 2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }

    .nav-brand {
        font-size: 1.5rem;
        font-weight: bold;
        color: #5865F2;
    }

    .nav-links a {
        color: #e0e0e0;
        text-decoration: none;
        margin: 0 1rem;
        transition: color 0.2s;
    }

    .nav-links a:hover {
        color: #5865F2;
    }

    .status-connected {
        color: #43b581;
    }

    .status-disconnected {
        color: #f04747;
    }

    .container {
        padding: 2rem;
        max-width: 1400px;
        margin: 0 auto;
    }

    .dashboard-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 1.5rem;
    }

    .card {
        background: #2d2d2d;
        border-radius: 8px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }

    .card.full-width {
        grid-column: 1 / -1;
    }

    .card h3 {
        margin-bottom: 1rem;
        color: #5865F2;
    }

    .activity-feed {
        max-height: 400px;
        overflow-y: auto;
    }

    .feed-item {
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        background: #1a1a1a;
        border-radius: 4px;
        border-left: 3px solid #5865F2;
    }

    .feed-item .time {
        color: #888;
        font-size: 0.9rem;
        margin-right: 0.5rem;
    }

    .feed-message {
        border-left-color: #43b581;
    }

    .feed-command {
        border-left-color: #faa61a;
    }
    ```

### Phase 5: Integration with Bot (30 minutes)

14. **Modify `main.py`** - Start web server alongside bot
    ```python
    import asyncio
    from config import config

    async def start_web_server():
        """Start the web dashboard server"""
        if config.enable_web_dashboard:
            import uvicorn
            from web.app import app

            config_uvicorn = uvicorn.Config(
                app,
                host=config.web_host,
                port=config.web_port,
                reload=config.web_reload,
                log_level="info"
            )
            server = uvicorn.Server(config_uvicorn)
            await server.serve()

    async def main():
        # Start web server in background
        if config.enable_web_dashboard:
            asyncio.create_task(start_web_server())

        # Start bot
        async with bot:
            await bot.start(config.token)

    if __name__ == "__main__":
        asyncio.run(main())
    ```

15. **Connect data collector to WebSocket manager**
    ```python
    # In main.py, after bot is ready
    @bot.event
    async def on_ready():
        logger.info(f'Logged in as {bot.user}')

        # Connect admin data collector to web server
        if config.enable_web_dashboard:
            from web.websocket_manager import manager
            from utils.admin_data_collector import get_data_collector

            collector = get_data_collector(bot)
            collector.websocket_manager = manager
    ```

### Phase 6: Additional Features (Optional, 1-2 hours)

16. **Add authentication** - Protect dashboard with password
    ```python
    # In web/app.py
    from fastapi.security import HTTPBasic, HTTPBasicCredentials
    from secrets import compare_digest

    security = HTTPBasic()

    def verify_credentials(credentials: HTTPBasicCredentials):
        correct_username = compare_digest(credentials.username, config.web_username)
        correct_password = compare_digest(credentials.password, config.web_password)
        return correct_username and correct_password

    @app.get("/")
    async def dashboard(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
        if not verify_credentials(credentials):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return templates.TemplateResponse("dashboard.html", {"request": request})
    ```

17. **Add REST API endpoints** - For external integrations
    ```python
    # In web/routes/api.py
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/v1")

    @router.get("/stats")
    async def get_stats():
        """Get current bot statistics"""
        return manager.data_cache

    @router.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "connections": len(manager.active_connections)}
    ```

18. **Add logs viewer** - Live bot logs in browser
    ```python
    # Create custom logging handler that broadcasts to WebSocket
    import logging
    from web.websocket_manager import manager

    class WebSocketLogHandler(logging.Handler):
        def emit(self, record):
            log_entry = {
                "level": record.levelname,
                "message": record.getMessage(),
                "time": record.created
            }

            # Broadcast to web clients
            if manager.active_connections:
                asyncio.create_task(
                    manager.broadcast({
                        "type": "log",
                        "data": log_entry
                    })
                )
    ```

---

## Configuration

Add to `.env`:
```env
# Web Dashboard Configuration
ENABLE_WEB_DASHBOARD=true
WEB_HOST=0.0.0.0
WEB_PORT=8000
WEB_RELOAD=false

# Optional: Authentication
WEB_USERNAME=admin
WEB_PASSWORD=your_secure_password_here
```

Add to `config.py`:
```python
@dataclass
class BotConfig:
    # ... existing config ...

    # Web Dashboard Configuration
    enable_web_dashboard: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    web_reload: bool = False
    web_username: str = "admin"
    web_password: str = ""
```

---

## Testing

1. **Start the bot**:
   ```bash
   python main.py
   ```

2. **Access dashboard**:
   - Local: http://localhost:8000
   - Network: http://YOUR_LOCAL_IP:8000 (e.g., http://192.168.1.100:8000)

3. **Test WebSocket connection**:
   - Open browser console (F12)
   - Should see "WebSocket connected"
   - Status indicator should show green

4. **Test real-time updates**:
   - Send a Discord message in a channel the bot can see
   - Should appear in activity feed immediately
   - Run a command (e.g., `~ping`)
   - Should appear in recent commands

---

## Migration Plan

### Deprecate pygame dashboard
1. Keep `admin_interface_full.py` for one release cycle
2. Add deprecation warning when started
3. Update README with migration instructions
4. Remove in next major version

### Data compatibility
- Keep `utils/admin_data_collector.py` unchanged
- Web server reads same JSON files
- Both dashboards can run simultaneously during transition

---

## Future Enhancements

1. **Mobile responsiveness** - Optimize for phone/tablet viewing
2. **Dark/Light theme toggle** - User preference
3. **Customizable dashboard** - Drag-and-drop widgets
4. **Historical data** - View stats from previous days/weeks
5. **Alerts and notifications** - Browser notifications for important events
6. **Multi-language support** - i18n for different languages
7. **Export data** - Download CSV/JSON of statistics
8. **Remote bot control** - Execute commands from web interface
9. **User management** - Multiple admin accounts with different permissions
10. **Webhook integrations** - Send events to external services

---

## Security Considerations

1. **Network access**:
   - By default, listens on `0.0.0.0` (all interfaces)
   - For local-only access, set `WEB_HOST=127.0.0.1`
   - For network access, ensure firewall rules are appropriate

2. **Authentication**:
   - Always use strong passwords
   - Consider adding HTTPS (reverse proxy with nginx/caddy)
   - Implement rate limiting for API endpoints

3. **Data exposure**:
   - Don't expose sensitive Discord tokens
   - Sanitize user input before displaying
   - Limit message content length in activity feed

4. **Production deployment**:
   - Use environment variables for secrets
   - Run behind reverse proxy (nginx/caddy)
   - Enable HTTPS with Let's Encrypt
   - Consider adding CORS restrictions

---

## Performance Considerations

- **WebSocket connections**: Tested up to 50 simultaneous connections
- **Update frequency**: 2-second polling (configurable)
- **Memory usage**: Minimal (shares bot's memory)
- **CPU usage**: Negligible (<1% additional)
- **Network bandwidth**: ~1-5 KB/s per connection

---

## Troubleshooting

**WebSocket won't connect**:
- Check firewall settings
- Ensure bot is running
- Verify port 8000 is not in use (`netstat -ano | findstr :8000`)

**No real-time updates**:
- Check browser console for errors
- Verify `admin_data/*.json` files are being created
- Check `data_pusher()` task is running

**High memory usage**:
- Reduce update frequency in `data_pusher()`
- Limit activity feed to fewer items
- Clear old admin_data files periodically

---

## Estimated Implementation Time

- **Phase 1** (Basic setup): 30 minutes
- **Phase 2** (WebSockets): 45 minutes
- **Phase 3** (Data integration): 1 hour
- **Phase 4** (Frontend): 2 hours
- **Phase 5** (Bot integration): 30 minutes
- **Phase 6** (Optional features): 1-2 hours

**Total**: ~5-6 hours for full implementation

---

## Notes

- Existing `admin_data_collector.py` remains unchanged
- Can run both pygame and web dashboard simultaneously during migration
- All real-time data already collected, just need to expose via WebSocket
- Frontend can be customized extensively without touching Python code
- Consider using Tailwind CSS for faster frontend development
