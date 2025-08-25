import logging
import tempfile
import os
from typing import Optional, Any
import pandas as pd

from ps3_api.constants import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE,
    MINIO_BUCKET_PDFS, MINIO_BUCKET_PARQUETS,
    AMQP_HOST, AMQP_PORT, AMQP_USERNAME, AMQP_PASSWORD, AMQP_VIRTUAL_HOST,
    AMQP_QUEUE_PDF_PROCESSING
)
from ps3_shared.lib.minio import MinioManager
from ps3_shared.lib.amqp import AMQPManager

logger = logging.getLogger(__name__)


class PDFService:
    """Servicio para manejar las operaciones de PDFs"""
    
    def __init__(self):
        self.minio_manager = MinioManager(
            MINIO_ENDPOINT, 
            MINIO_ACCESS_KEY, 
            MINIO_SECRET_KEY, 
            MINIO_SECURE
        )
        self.amqp_manager = AMQPManager(
            AMQP_HOST,
            AMQP_PORT,
            AMQP_USERNAME,
            AMQP_PASSWORD,
            AMQP_VIRTUAL_HOST
        )
        
        # Asegurar que los buckets existan
        self._ensure_buckets_exist()
    
    def _ensure_buckets_exist(self):
        """Asegurar que los buckets de MinIO existan"""
        try:
            self.minio_manager.make_bucket(MINIO_BUCKET_PDFS)
            self.minio_manager.make_bucket(MINIO_BUCKET_PARQUETS)
            logger.info("Buckets de MinIO verificados/creados")
        except Exception as e:
            logger.error(f"Error al crear buckets de MinIO: {e}")
    
    def upload_pdf(self, file_content: bytes, filename: str, task_id: str) -> Optional[str]:
        """Subir un PDF a MinIO y retornar la ruta"""
        try:
            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            # Generar nombre único para el archivo en MinIO
            # Estructura: {task_id}/pdfs/{filename}
            minio_object_name = f"{task_id}/pdfs/{filename}"
            
            # Subir archivo a MinIO
            self.minio_manager.upload_file(
                MINIO_BUCKET_PDFS,
                minio_object_name,
                temp_file_path
            )
            
            # Limpiar archivo temporal
            os.unlink(temp_file_path)
            
            logger.info(f"PDF subido exitosamente: {minio_object_name}")
            return minio_object_name
            
        except Exception as e:
            logger.error(f"Error al subir PDF: {e}")
            return None
    
    def publish_processing_message(self, task_id: str, filename: str, minio_path: str) -> bool:
        """Publicar mensaje en la cola AMQP para procesamiento"""
        try:
            # Conectar a AMQP
            self.amqp_manager.connect()
            
            # Declarar cola
            self.amqp_manager.declare_queue(AMQP_QUEUE_PDF_PROCESSING)
            
            # Crear mensaje
            message = {
                "task_id": task_id,
                "filename": filename,
                "minio_path": minio_path,
                "timestamp": pd.Timestamp.now().isoformat()
            }
            
            # Publicar mensaje
            self.amqp_manager.publish(AMQP_QUEUE_PDF_PROCESSING, str(message))
            
            logger.info(f"Mensaje publicado en cola AMQP para tarea: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error al publicar mensaje AMQP: {e}")
            return False
    
    def get_parquet_data(self, task_id: str, data_type: str = "odds_path") -> Optional[Any]:
        """Obtener datos del archivo parquet de una tarea por tipo"""
        try:
            # Buscar archivo parquet específico en MinIO
            # Estructura: {task_id}/parquets/{data_type}_{filename}
            parquet_files = self.minio_manager.list_files(
                MINIO_BUCKET_PARQUETS, 
                prefix=f"{task_id}/parquets/{data_type}_"
            )
            
            if not parquet_files:
                logger.warning(f"No se encontraron archivos parquet {data_type} para la tarea: {task_id}")
                return None
            
            # Tomar el primer archivo parquet encontrado del tipo especificado
            parquet_file = parquet_files[0]
            
            # Crear archivo temporal para descargar
            with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as temp_file:
                temp_file_path = temp_file.name
            
            # Descargar archivo de MinIO
            self.minio_manager.download_file(
                MINIO_BUCKET_PARQUETS,
                parquet_file,
                temp_file_path
            )
            
            # Leer archivo parquet con pandas
            df = pd.read_parquet(temp_file_path)
            
            # Limpiar archivo temporal
            os.unlink(temp_file_path)
            
            # Convertir DataFrame a formato JSON
            data = df.to_dict(orient="records")
            
            logger.info(f"Datos parquet {data_type} obtenidos para tarea {task_id}: {len(data)} registros")
            return data
            
        except Exception as e:
            logger.error(f"Error al obtener datos parquet {data_type} para tarea {task_id}: {e}")
            return None
    
    def download_parquet_file(self, task_id: str, output_path: str, data_type: str = "odds_path") -> bool:
        """Descargar archivo parquet de una tarea por tipo"""
        try:
            # Buscar archivo parquet específico en MinIO
            # Estructura: {task_id}/parquets/{data_type}_{filename}
            parquet_files = self.minio_manager.list_files(
                MINIO_BUCKET_PARQUETS, 
                prefix=f"{task_id}/parquets/{data_type}_"
            )
            
            if not parquet_files:
                logger.warning(f"No se encontraron archivos parquet {data_type} para la tarea: {task_id}")
                return False
            
            # Tomar el primer archivo parquet encontrado del tipo especificado
            parquet_file = parquet_files[0]
            
            # Descargar archivo de MinIO
            self.minio_manager.download_file(
                MINIO_BUCKET_PARQUETS,
                parquet_file,
                output_path
            )
            
            logger.info(f"Archivo parquet {data_type} descargado para tarea {task_id}: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error al descargar archivo parquet {data_type} para tarea {task_id}: {e}")
            return False
    
    def list_task_files(self, task_id: str) -> dict:
        """Listar todos los archivos de una tarea específica"""
        try:
            task_files = {}
            
            # Listar archivos PDF
            pdf_files = self.minio_manager.list_files(
                MINIO_BUCKET_PDFS, 
                prefix=f"{task_id}/pdfs/"
            )
            task_files["pdfs"] = pdf_files
            
            # Listar archivos parquet
            parquet_files = self.minio_manager.list_files(
                MINIO_BUCKET_PARQUETS, 
                prefix=f"{task_id}/parquets/"
            )
            task_files["parquets"] = parquet_files
            
            # Listar otros archivos que puedan existir
            other_files = self.minio_manager.list_files(
                MINIO_BUCKET_PDFS, 
                prefix=f"{task_id}/"
            )
            # Filtrar solo archivos que no sean PDFs
            other_files = [f for f in other_files if not f.startswith(f"{task_id}/pdfs/")]
            task_files["others"] = other_files
            
            logger.info(f"Archivos listados para tarea {task_id}: {len(task_files)} categorías")
            return task_files
            
        except Exception as e:
            logger.error(f"Error al listar archivos de tarea {task_id}: {e}")
            return {}
    
    def get_task_structure_info(self, task_id: str) -> dict:
        """Obtener información sobre la estructura de archivos de una tarea"""
        try:
            files = self.list_task_files(task_id)
            
            structure_info = {
                "task_id": task_id,
                "structure": {
                    "pdfs": {
                        "count": len(files.get("pdfs", [])),
                        "files": files.get("pdfs", [])
                    },
                    "parquets": {
                        "count": len(files.get("parquets", [])),
                        "files": files.get("parquets", [])
                    },
                    "others": {
                        "count": len(files.get("others", [])),
                        "files": files.get("others", [])
                    }
                },
                "total_files": sum(len(files.get(cat, [])) for cat in ["pdfs", "parquets", "others"])
            }
            
            return structure_info
            
        except Exception as e:
            logger.error(f"Error al obtener información de estructura para tarea {task_id}: {e}")
            return {"task_id": task_id, "error": str(e)}
    
    def close(self):
        """Cerrar conexiones"""
        try:
            self.amqp_manager.close()
            logger.info("Conexiones cerradas")
        except Exception as e:
            logger.error(f"Error al cerrar conexiones: {e}") 