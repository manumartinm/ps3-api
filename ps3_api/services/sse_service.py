import logging
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class SSEManager:
    """Manager para manejar conexiones SSE en la API"""
    
    def __init__(self):
        self.active_connections: Dict[str, List[asyncio.Queue]] = {}
        self.event_history: Dict[str, list] = {}
    
    async def register_connection(self, task_id: str) -> asyncio.Queue:
        """Registrar una nueva conexión SSE para una tarea"""
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
            self.event_history[task_id] = []
        
        # Crear nueva cola para esta conexión
        connection_queue = asyncio.Queue()
        self.active_connections[task_id].append(connection_queue)
        
        logger.info(f"Nueva conexión SSE registrada para tarea: {task_id}. Total conexiones: {len(self.active_connections[task_id])}")
        return connection_queue
    
    async def unregister_connection(self, task_id: str, connection_queue: asyncio.Queue):
        """Desregistrar una conexión SSE específica"""
        if task_id in self.active_connections:
            try:
                self.active_connections[task_id].remove(connection_queue)
                logger.info(f"Conexión SSE desregistrada para tarea: {task_id}. Conexiones restantes: {len(self.active_connections[task_id])}")
                
                # Si no hay más conexiones, limpiar la entrada
                if not self.active_connections[task_id]:
                    del self.active_connections[task_id]
                    logger.info(f"Todas las conexiones SSE cerradas para tarea: {task_id}")
            except ValueError:
                logger.warning(f"Intento de desregistrar conexión SSE inexistente para tarea: {task_id}")
    
    async def send_event_to_task(self, task_id: str, event_type: str, data: Dict[str, Any]):
        """Enviar un evento SSE a todas las conexiones de una tarea"""
        try:
            event = {
                "id": f"{task_id}_{int(datetime.now().timestamp())}",
                "event": event_type,
                "data": json.dumps(data),
                "timestamp": datetime.now().isoformat()
            }
            
            # Agregar a historial
            if task_id in self.event_history:
                self.event_history[task_id].append(event)
                # Mantener solo los últimos 100 eventos
                if len(self.event_history[task_id]) > 100:
                    self.event_history[task_id] = self.event_history[task_id][-100:]
            
            # Enviar a todas las conexiones activas
            if task_id in self.active_connections:
                active_connections = self.active_connections[task_id].copy()
                for connection_queue in active_connections:
                    try:
                        await connection_queue.put(event)
                    except Exception as e:
                        logger.error(f"Error enviando evento a conexión SSE: {e}")
                        # Remover conexión problemática
                        await self.unregister_connection(task_id, connection_queue)
                
                logger.debug(f"Evento SSE enviado a {len(active_connections)} conexiones de tarea {task_id}: {event_type}")
            
        except Exception as e:
            logger.error(f"Error enviando evento SSE a tarea {task_id}: {e}")
    
    async def send_progress_event(self, task_id: str, stage: str, progress: int, message: str, **kwargs):
        """Enviar evento de progreso"""
        data = {
            "stage": stage,
            "progress": progress,
            "message": message,
            **kwargs
        }
        await self.send_event_to_task(task_id, "progress", data)
    
    async def send_status_event(self, task_id: str, status: str, message: str, **kwargs):
        """Enviar evento de cambio de estado"""
        data = {
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        await self.send_event_to_task(task_id, "status", data)
    
    async def send_error_event(self, task_id: str, error: str, details: str = None):
        """Enviar evento de error"""
        data = {
            "error": error,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_event_to_task(task_id, "error", data)
    
    async def send_completion_event(self, task_id: str, results: Dict[str, Any]):
        """Enviar evento de completado"""
        data = {
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_event_to_task(task_id, "completion", data)
    
    def get_event_history(self, task_id: str) -> list:
        """Obtener historial de eventos de una tarea"""
        return self.event_history.get(task_id, [])
    
    def get_active_connections_count(self, task_id: str) -> int:
        """Obtener número de conexiones activas para una tarea"""
        return len(self.active_connections.get(task_id, []))
    
    async def close(self):
        """Cerrar todas las conexiones SSE"""
        try:
            for task_id in list(self.active_connections.keys()):
                for connection_queue in self.active_connections[task_id]:
                    await self.unregister_connection(task_id, connection_queue)
            logger.info("Manager SSE cerrado")
        except Exception as e:
            logger.error(f"Error cerrando manager SSE: {e}")


# Instancia global del manager SSE
sse_manager = SSEManager() 