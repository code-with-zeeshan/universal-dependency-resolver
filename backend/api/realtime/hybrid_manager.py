"""
Hybrid WebSocket/Socket.IO Manager
Automatically switches between protocols based on client support
"""
import asyncio
from typing import Dict, Set, Optional
import socketio
from datetime import datetime
import json


class SocketIOConnection:
    """Socket.IO implementation"""

    def __init__(self, sio: socketio.AsyncServer, sid: str):
        self.sio = sio
        self.sid = sid
        self.connection_type = "socketio"

    async def send(self, message: dict):
        event_type = message.get('type', 'message')
        await self.sio.emit(event_type, message, to=self.sid)

    async def close(self):
        await self.sio.disconnect(self.sid)


class HybridConnectionManager:
    """Manages Socket.IO connections"""

    def __init__(self):
        self.connections: Dict[str, SocketIOConnection] = {}
        self.subscriptions: Dict[str, Set[str]] = {}
        self.operation_progress: Dict[str, dict] = {}
        self._sio: Optional[socketio.AsyncServer] = None
        self.connection_stats = {
            'socketio': 0,
            'total': 0
        }

    @property
    def sio(self) -> socketio.AsyncServer:
        if self._sio is None:
            self._sio = socketio.AsyncServer(
                async_mode='asgi',
                cors_allowed_origins='*',
                logger=True,
                engineio_logger=True
            )
            self._setup_socketio_handlers()
        return self._sio

    def _setup_socketio_handlers(self):
        @self.sio.event
        async def connect(sid, environ):
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

            if sid in self.subscriptions:
                del self.subscriptions[sid]

    def get_connection(self, client_id: str) -> Optional[SocketIOConnection]:
        return self.connections.get(client_id)

    async def send_to_client(self, client_id: str, message: dict):
        conn = self.get_connection(client_id)
        if conn:
            try:
                await conn.send(message)
            except Exception as e:
                print(f"Failed to send to {client_id}: {e}")
                await self.disconnect(client_id)

    async def broadcast_to_operation(self, operation_id: str, message: dict):
        channel = f"operation:{operation_id}"

        if message.get('type') in ['progress', 'resolution_progress']:
            self.operation_progress[operation_id] = message

        for client_id, channels in self.subscriptions.items():
            if channel in channels:
                await self.send_to_client(client_id, message)

    def subscribe(self, client_id: str, operation_id: str):
        if client_id not in self.subscriptions:
            self.subscriptions[client_id] = set()

        channel = f"operation:{operation_id}"
        self.subscriptions[client_id].add(channel)

        if operation_id in self.operation_progress:
            asyncio.create_task(
                self.send_to_client(client_id, self.operation_progress[operation_id])
            )

    def unsubscribe(self, client_id: str, operation_id: str):
        if client_id in self.subscriptions:
            channel = f"operation:{operation_id}"
            self.subscriptions[client_id].discard(channel)

    async def disconnect(self, client_id: str):
        if client_id in self.connections:
            conn = self.connections[client_id]

            if hasattr(conn, 'connection_type'):
                self.connection_stats[conn.connection_type] -= 1
                self.connection_stats['total'] -= 1

            try:
                await conn.close()
            except Exception:
                pass

            del self.connections[client_id]

        if client_id in self.subscriptions:
            del self.subscriptions[client_id]

    def get_stats(self) -> dict:
        return {
            **self.connection_stats,
            'active_operations': len(self.operation_progress),
            'timestamp': datetime.utcnow().isoformat()
        }


# Global manager instance
hybrid_manager = HybridConnectionManager()
