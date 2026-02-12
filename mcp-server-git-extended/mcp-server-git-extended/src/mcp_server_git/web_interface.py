from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime
import json
import asyncio
from contextlib import asynccontextmanager
import uvicorn
import socket
import os
import logging
from .models import GitLog, engine
from .async_models import get_logs_async, create_db_and_tables_async


# WebSocket connection manager
class ConnectionManager:
    def __init__(self, max_connections: int = 100):
        self.active_connections: List[WebSocket] = []
        self.max_connections = max_connections

    async def connect(self, websocket: WebSocket):
        if len(self.active_connections) >= self.max_connections:
            await websocket.close(code=1008, reason="Connection limit reached")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except RuntimeError:
                # Mark for removal if connection failed
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - create tables if needed
    await create_db_and_tables_async()
    yield
    # Shutdown
    pass


app = FastAPI(lifespan=lifespan, title="Git MCP Extended Logs")

# Setup logging
logger = logging.getLogger(__name__)

# Setup templates and static files
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    connected = await manager.connect(websocket)
    if not connected:
        return
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/logs")
async def get_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    command: Optional[str] = None,
    status: Optional[str] = None
):
    logs = await get_logs_async(skip=skip, limit=limit, command=command, status=status)
    # Parse JSON arguments for cleaner API response
    result = []
    for log in logs:
        log_dict = log.model_dump()
        try:
            # Parse arguments JSON string to actual dict
            log_dict['arguments'] = json.loads(log_dict['arguments'])
        except (json.JSONDecodeError, TypeError):
            # Keep as string if parsing fails
            pass
        result.append(log_dict)
    return result


@app.post("/api/notify")
async def notify_new_log(request: Request):
    """Notify all connected clients about new log - localhost only"""
    # Security: Only accept requests from localhost
    client_host = request.client.host
    if client_host not in ["127.0.0.1", "::1", "localhost"]:
        raise HTTPException(
            status_code=403,
            detail="Access denied: This endpoint is only accessible from localhost"
        )
    
    await manager.broadcast(json.dumps({"type": "new_log"}))
    return {"status": "notified"}


def find_free_port(start_port: int = 5555, max_attempts: int = 10) -> int:
    """Find a free port starting from start_port"""
    # Check if port is specified via environment variable
    env_port = os.getenv('MCP_GIT_WEB_PORT')
    if env_port:
        try:
            start_port = int(env_port)
        except ValueError:
            logger.warning(f"Invalid MCP_GIT_WEB_PORT value: {env_port}, using default {start_port}")
    
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port in range {start_port}-{start_port + max_attempts}. Please check if other services are using these ports.")


def start_web_server(port: Optional[int] = None):
    """Start the FastAPI web server"""
    if port is None:
        port = find_free_port()
    
    print(f"Starting Git MCP Extended Logs web interface on http://localhost:{port}")
    
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="error",  # Reduce logging noise
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    start_web_server()