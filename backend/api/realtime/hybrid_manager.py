"""
Hybrid WebSocket/Socket.IO Manager
Automatically switches between protocols based on client support
"""
import asyncio
from typing import Dict, Set, Optional, Protocol
from abc import ABC, abstractmethod
from fastapi import WebSocket
import socketio
from datetime import datetime
import json

class RealtimeConnection(ABC):
    """Abstract base for realtime connections"""
    
    @abstractmethod
    async def send(self, message: dict):
        pass
    
    @abstractmethod
    async def receive(self) -> dict:
        pass
    
    @abstractmethod
    async def close(self):
        pass

class WebSocketConnection(RealtimeConnection):
    """Pure WebSocket implementation"""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.connection_type = "websocket"
    
    async def send(self, message: dict):
        await self.websocket.send_json(message)
    
    async def receive(self) -> dict:
        return await self.websocket.receive_json()
    
    async def close(self):
        await self.websocket.close()

class SocketIOConnection(RealtimeConnection):
    """Socket.IO implementation"""
    
    def __init__(self, sio: socketio.AsyncServer, sid: str):
        self.sio = sio
        self.sid = sid
        self.connection_type = "socketio"
        self.message_queue = asyncio.Queue()
    
    async def send(self, message: dict):
        event_type = message.get('type', 'message')
        await self.sio.emit(event_type, message, to=self.sid)
    
    async def receive(self) -> dict:
        # Socket.IO uses event-based messaging
        return await self.message_queue.get()
    
    async def close(self):
        await self.sio.disconnect(self.sid)

class HybridConnectionManager:
    """Manages both WebSocket and Socket.IO connections"""
    
    def __init__(self):
        # Connection storage
        self.connections: Dict[str, RealtimeConnection] = {}
        self.subscriptions: Dict[str, Set[str]] = {}
        
        # Operation progress tracking
        self.operation_progress: Dict[str, dict] = {}
        
        # Socket.IO server instance (lazy loaded)
        self._sio: Optional[socketio.AsyncServer] = None
        
        # Metrics
        self.connection_stats = {
            'websocket': 0,
            'socketio': 0,
            'total': 0
        }
    
    @property
    def sio(self) -> socketio.AsyncServer:
        """Lazy load Socket.IO server"""
        if self._sio is None:
            self._sio = socketio.AsyncServer(
                async_mode='asgi',
                cors_allowed_origins='*',  # Configure properly for production
                logger=True,
                engineio_logger=True
            )
            self._setup_socketio_handlers()
        return self._sio
    
    def _setup_socketio_handlers(self):
        """Setup Socket.IO event handlers"""
        
        @self.sio.event
        async def connect(sid, environ):
            # Create Socket.IO connection wrapper
            conn = SocketIOConnection(self.sio, sid)
            self.connections[sid] = conn
            self.connection_stats['socketio'] += 1
            self.connection_stats['total'] += 1
            
            await conn.send({
                'type': 'connection',
                'status': 'connected',
                'client_id': sid,
                'connection_type': 'socketio',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        @self.sio.event
        async def disconnect(sid):
            if sid in self.connections:
                del self.connections[sid]
                self.connection_stats['socketio'] -= 1
                self.connection_stats['total'] -= 1
            
            # Clean up subscriptions
            if sid in self.subscriptions:
                del self.subscriptions[sid]
        
        @self.sio.event
        async def message(sid, data):
            # Queue message for receive() method
            if sid in self.connections:
                conn = self.connections[sid]
                if hasattr(conn, 'message_queue'):
                    await conn.message_queue.put(data)
    
    async def accept_websocket(self, websocket: WebSocket, client_id: str) -> WebSocketConnection:
        """Accept a WebSocket connection"""
        await websocket.accept()
        
        conn = WebSocketConnection(websocket)
        self.connections[client_id] = conn
        self.connection_stats['websocket'] += 1
        self.connection_stats['total'] += 1
        
        return conn
    
    def get_connection(self, client_id: str) -> Optional[RealtimeConnection]:
        """Get connection by client ID"""
        return self.connections.get(client_id)
    
    async def send_to_client(self, client_id: str, message: dict):
        """Send message to specific client"""
        conn = self.get_connection(client_id)
        if conn:
            try:
                await conn.send(message)
            except Exception as e:
                print(f"Failed to send to {client_id}: {e}")
                await self.disconnect(client_id)
    
    async def broadcast_to_operation(self, operation_id: str, message: dict):
        """Broadcast to all clients subscribed to an operation"""
        channel = f"operation:{operation_id}"
        
        # Store progress for late joiners
        if message.get('type') in ['progress', 'resolution_progress']:
            self.operation_progress[operation_id] = message
        
        # Send to all subscribers
        for client_id, channels in self.subscriptions.items():
            if channel in channels:
                await self.send_to_client(client_id, message)
    
    def subscribe(self, client_id: str, operation_id: str):
        """Subscribe client to operation updates"""
        if client_id not in self.subscriptions:
            self.subscriptions[client_id] = set()
        
        channel = f"operation:{operation_id}"
        self.subscriptions[client_id].add(channel)
        
        # Send current progress if exists
        if operation_id in self.operation_progress:
            asyncio.create_task(
                self.send_to_client(client_id, self.operation_progress[operation_id])
            )
    
    def unsubscribe(self, client_id: str, operation_id: str):
        """Unsubscribe client from operation"""
        if client_id in self.subscriptions:
            channel = f"operation:{operation_id}"
            self.subscriptions[client_id].discard(channel)
    
    async def disconnect(self, client_id: str):
        """Disconnect a client"""
        if client_id in self.connections:
            conn = self.connections[client_id]
            
            # Update stats
            if hasattr(conn, 'connection_type'):
                self.connection_stats[conn.connection_type] -= 1
                self.connection_stats['total'] -= 1
            
            try:
                await conn.close()
            except:
                pass
            
            del self.connections[client_id]
        
        # Clean up subscriptions
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            **self.connection_stats,
            'active_operations': len(self.operation_progress),
            'timestamp': datetime.utcnow().isoformat()
        }

# Global manager instance
hybrid_manager = HybridConnectionManager()