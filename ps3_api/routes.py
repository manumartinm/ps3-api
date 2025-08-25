import hashlib
import logging
import os
import time
import asyncio
from collections import defaultdict
from functools import wraps
from typing import Callable
import tempfile

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ps3_api.constants import API_KEY
from ps3_api.entities import (
    PDFUploadResponse, PDFDataResponse, TaskResponse, TaskListResponse, TaskStructureResponse
)
from ps3_shared.entities.task import TaskCreate
from ps3_api.services import TaskService, PDFService
from ps3_api.services.sse_service import sse_manager

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger("app")

rate_limit_storage = defaultdict(list)


def rate_limit(max_requests: int = 100, window_seconds: int = 3600) -> Callable:
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request") or args[0]
            client_ip = request.client.host

            current_time = time.time()

            rate_limit_storage[client_ip] = [
                req_time
                for req_time in rate_limit_storage[client_ip]
                if current_time - req_time < window_seconds
            ]

            if len(rate_limit_storage[client_ip]) >= max_requests:
                raise HTTPException(
                    status_code=429, detail="Rate limit exceeded. Try again later."
                )

            rate_limit_storage[client_ip].append(current_time)
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    token = credentials.credentials

    if not token or token != API_KEY:
        raise HTTPException(
            status_code=401, detail="Invalid or missing authentication token"
        )

    return token


async def validate_pdf(file: UploadFile) -> UploadFile:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    return file


def generate_secure_random_hash(length: int = 32) -> str:
    random_bytes = os.urandom(32)

    sha256_hash = hashlib.sha256(random_bytes).hexdigest()

    return sha256_hash[:length]


@router.post("/upload-pdf", response_model=PDFUploadResponse)
@rate_limit(max_requests=50, window_seconds=3600)
async def upload_pdf(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    try:
        validated_file = await validate_pdf(file)
        
        task_id = generate_secure_random_hash()
        
        file_content = await validated_file.read()
        
        task_service = TaskService()
        pdf_service = PDFService()
        
        try:
            task_data = TaskCreate(filename=validated_file.filename)
            task = task_service.create_task(task_data, task_id)
            
            if not task:
                raise HTTPException(
                    status_code=500, 
                    detail="Error al crear la tarea en la base de datos"
                )
            
            minio_path = pdf_service.upload_pdf(file_content, validated_file.filename, task_id)
            
            if not minio_path:
                task_service.update_task_status(
                    task_id, 
                    "failed", 
                    error_message="Error al subir archivo a MinIO"
                )
                raise HTTPException(
                    status_code=500, 
                    detail="Error al subir el archivo a MinIO"
                )
            
            task_service.update_task_paths(task_id, minio_path=minio_path)
            
            message_published = pdf_service.publish_processing_message(
                task_id, 
                validated_file.filename, 
                minio_path
            )
            
            if not message_published:
                logger.warning(f"Mensaje AMQP no pudo ser publicado para tarea: {task_id}")
            
            updated_task = task_service.get_task_by_id(task_id)
            
            return PDFUploadResponse(
                success=True,
                message="PDF subido exitosamente y tarea creada",
                task=updated_task
            )
            
        finally:
            task_service.close()
            pdf_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado en upload_pdf: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks", response_model=TaskListResponse)
@rate_limit(max_requests=100, window_seconds=3600)
async def get_tasks(token: str = Depends(verify_token)):
    try:
        task_service = TaskService()
        
        try:
            tasks = task_service.get_all_tasks()
            
            return TaskListResponse(
                success=True,
                message=f"Se encontraron {len(tasks)} tareas",
                data=tasks,
                total=len(tasks)
            )
            
        finally:
            task_service.close()
            
    except Exception as e:
        logger.error(f"Error al obtener tareas: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
@rate_limit(max_requests=100, window_seconds=3600)
async def get_task(task_id: str, token: str = Depends(verify_token)):
    """
    Endpoint que devuelve una tarea específica por ID
    """
    try:
        task_service = TaskService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            return TaskResponse(
                success=True,
                message="Tarea encontrada exitosamente",
                data=task
            )
            
        finally:
            task_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}/data", response_model=PDFDataResponse)
@rate_limit(max_requests=100, window_seconds=3600)
async def get_task_data(
    task_id: str, 
    data_type: str = "odds_path",  # "odds_path" o "explanations"
    token: str = Depends(verify_token)
):
    """
    Endpoint que devuelve los datos de una tarea en formato JSON leyendo el parquet especificado
    - data_type: "odds_path" para datos del odds path calculator, "explanations" para explicaciones
    """
    try:
        task_service = TaskService()
        pdf_service = PDFService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            if task.status.value != "completed":
                raise HTTPException(
                    status_code=400, 
                    detail=f"La tarea {task_id} no está completada. Estado actual: {task.status.value}"
                )
            
            # Validar tipo de datos solicitado
            if data_type not in ["odds_path", "explanations"]:
                raise HTTPException(
                    status_code=400,
                    detail="data_type debe ser 'odds_path' o 'explanations'"
                )
            
            # Obtener datos del archivo parquet específico
            data = pdf_service.get_parquet_data(task_id, data_type)
            
            if data is None:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No se encontraron datos {data_type} para la tarea {task_id}"
                )
            
            return PDFDataResponse(
                success=True,
                message=f"Datos {data_type} obtenidos exitosamente",
                data=data,
                task_id=task_id
            )
            
        finally:
            task_service.close()
            pdf_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener datos {data_type} de tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}/parquet")
@rate_limit(max_requests=50, window_seconds=3600)
async def download_task_parquet(
    task_id: str, 
    data_type: str = "odds_path",  # "odds_path" o "explanations"
    token: str = Depends(verify_token)
):
    """
    Endpoint que devuelve el archivo parquet de una tarea para descarga
    - data_type: "odds_path" para datos del odds path calculator, "explanations" para explicaciones
    """
    try:
        # Verificar que la tarea existe y está completada
        task_service = TaskService()
        pdf_service = PDFService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            if task.status.value != "completed":
                raise HTTPException(
                    status_code=400, 
                    detail=f"La tarea {task_id} no está completada. Estado actual: {task.status.value}"
                )
            
            # Validar tipo de datos solicitado
            if data_type not in ["odds_path", "explanations"]:
                raise HTTPException(
                    status_code=400,
                    detail="data_type debe ser 'odds_path' o 'explanations'"
                )
            
            # Crear archivo temporal para la descarga
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".parquet")
            temp_file_path = temp_file.name
            temp_file.close()
            
            try:
                # Descargar archivo parquet específico
                success = pdf_service.download_parquet_file(task_id, temp_file_path, data_type)
                
                if not success:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"No se pudo descargar el archivo {data_type} para la tarea {task_id}"
                    )
                
                # Retornar archivo para descarga
                filename = f"task_{task_id}_{data_type}.parquet"
                
                return FileResponse(
                    path=temp_file_path,
                    filename=filename,
                    media_type="application/octet-stream"
                )
                
            finally:
                # Limpiar archivo temporal después de la respuesta
                import os
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
        finally:
            task_service.close()
            pdf_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al descargar parquet {data_type} de tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}/data/all", response_model=dict)
@rate_limit(max_requests=100, window_seconds=3600)
async def get_all_task_data(task_id: str, token: str = Depends(verify_token)):
    """
    Endpoint que devuelve ambos tipos de datos (odds_path y explanations) de una tarea
    """
    try:
        task_service = TaskService()
        pdf_service = PDFService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            if task.status.value != "completed":
                raise HTTPException(
                    status_code=400, 
                    detail=f"La tarea {task_id} no está completada. Estado actual: {task.status.value}"
                )
            
            # Obtener ambos tipos de datos
            odds_path_data = pdf_service.get_parquet_data(task_id, "odds_path")
            explanations_data = pdf_service.get_parquet_data(task_id, "explanations")
            
            if odds_path_data is None and explanations_data is None:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No se encontraron datos para la tarea {task_id}"
                )
            
            result = {
                "task_id": task_id,
                "odds_path": odds_path_data if odds_path_data is not None else [],
                "explanations": explanations_data if explanations_data is not None else [],
                "summary": {
                    "odds_path_count": len(odds_path_data) if odds_path_data is not None else 0,
                    "explanations_count": len(explanations_data) if explanations_data is not None else 0
                }
            }
            
            return {
                "success": True,
                "message": "Todos los datos obtenidos exitosamente",
                "data": result
            }
            
        finally:
            task_service.close()
            pdf_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener todos los datos de tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}/structure", response_model=TaskStructureResponse)
@rate_limit(max_requests=100, window_seconds=3600)
async def get_task_structure(task_id: str, token: str = Depends(verify_token)):
    """
    Endpoint que devuelve la información de la estructura de archivos de una tarea
    """
    try:
        # Verificar que la tarea existe
        task_service = TaskService()
        pdf_service = PDFService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            # Obtener información de la estructura de archivos
            structure_info = pdf_service.get_task_structure_info(task_id)
            
            if "error" in structure_info:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Error al obtener estructura de archivos: {structure_info['error']}"
                )
            
            return TaskStructureResponse(
                success=True,
                message="Estructura de archivos obtenida exitosamente",
                data=TaskStructureInfo(**structure_info)
            )
            
        finally:
            task_service.close()
            pdf_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener estructura de tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    task_id: str,
    token: str = Depends(verify_token)
):
    """
    Endpoint SSE para streaming de eventos en tiempo real de una tarea
    """
    try:
        # Verificar que la tarea existe
        task_service = TaskService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            # Registrar conexión SSE
            connection_queue = await sse_manager.register_connection(task_id)
            
            # Enviar evento inicial
            await sse_manager.send_status_event(
                task_id, 
                "connected", 
                f"Conectado a eventos SSE de tarea {task_id}"
            )
            
            try:
                # Stream de eventos
                while True:
                    try:
                        # Esperar evento con timeout
                        event = await asyncio.wait_for(connection_queue.get(), timeout=30.0)
                        
                        # Formatear evento SSE
                        sse_data = f"id: {event['id']}\n"
                        sse_data += f"event: {event['event']}\n"
                        sse_data += f"data: {event['data']}\n"
                        sse_data += f"timestamp: {event['timestamp']}\n\n"
                        
                        yield sse_data
                        
                    except asyncio.TimeoutError:
                        # Enviar keep-alive
                        yield f": keep-alive\n\n"
                        
            except asyncio.CancelledError:
                logger.info(f"Conexión SSE cancelada para tarea: {task_id}")
                
            finally:
                # Desregistrar conexión
                await sse_manager.unregister_connection(task_id, connection_queue)
                
        finally:
            task_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en stream SSE para tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/tasks/{task_id}/events/history")
async def get_task_events_history(
    task_id: str,
    token: str = Depends(verify_token)
):
    """
    Endpoint para obtener el historial de eventos de una tarea
    """
    try:
        # Verificar que la tarea existe
        task_service = TaskService()
        
        try:
            task = task_service.get_task_by_id(task_id)
            
            if not task:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Tarea con ID {task_id} no encontrada"
                )
            
            # Obtener historial de eventos
            events = sse_manager.get_event_history(task_id)
            
            return {
                "success": True,
                "message": f"Historial de eventos obtenido para tarea {task_id}",
                "data": {
                    "task_id": task_id,
                    "events": events,
                    "total_events": len(events)
                }
            }
            
        finally:
            task_service.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo historial de eventos para tarea {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno del servidor"
        )


@router.get("/health")
async def health_check():
    data = {"status": "healthy", "timestamp": time.time()}

    return JSONResponse(
        content=data,
        headers={
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
        },
    )
