import logging
from datetime import datetime
from typing import List, Optional
from bson import ObjectId

from ps3_api.constants import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION_TASKS
from ps3_shared.entities.task import Task, TaskCreate, TaskStatus
from ps3_shared.lib.mongo import MongoManager

logger = logging.getLogger(__name__)


class TaskService:
    """Servicio para manejar las operaciones de tareas"""
    
    def __init__(self):
        self.mongo_manager = MongoManager(MONGO_URI, MONGO_DB_NAME)
        self.tasks_collection = MONGO_COLLECTION_TASKS
    
    def create_task(self, task_data: TaskCreate, task_id: str) -> Optional[Task]:
        """Crear una nueva tarea en MongoDB"""
        try:
            task_dict = task_data.model_dump()
            task_dict["id"] = task_id
            task_dict["created_at"] = datetime.now()
            task_dict["updated_at"] = datetime.now()
            
            inserted_id = self.mongo_manager.insert_one(self.tasks_collection, task_dict)
            if inserted_id:
                logger.info(f"Tarea creada con ID: {task_id}")
                return self.get_task_by_id(task_id)
            return None
        except Exception as e:
            logger.error(f"Error al crear tarea: {e}")
            return None
    
    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Obtener una tarea por su ID"""
        try:
            task_dict = self.mongo_manager.find_one(self.tasks_collection, {"id": task_id})
            if task_dict:
                # Convertir ObjectId a string si existe
                if "_id" in task_dict:
                    del task_dict["_id"]
                return Task(**task_dict)
            return None
        except Exception as e:
            logger.error(f"Error al obtener tarea {task_id}: {e}")
            return None
    
    def get_all_tasks(self) -> List[Task]:
        """Obtener todas las tareas"""
        try:
            tasks_dict = self.mongo_manager.find_many(self.tasks_collection, {})
            tasks = []
            for task_dict in tasks_dict:
                if "_id" in task_dict:
                    del task_dict["_id"]
                tasks.append(Task(**task_dict))
            return tasks
        except Exception as e:
            logger.error(f"Error al obtener tareas: {e}")
            return []
    
    def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> bool:
        """Actualizar el estado de una tarea"""
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now(),
                **kwargs
            }
            
            if status == TaskStatus.PROCESSING:
                update_data["processing_started_at"] = datetime.now()
            elif status == TaskStatus.COMPLETED or status == TaskStatus.FAILED:
                update_data["completed_at"] = datetime.now()
            
            modified_count = self.mongo_manager.update_one(
                self.tasks_collection, 
                {"id": task_id}, 
                update_data
            )
            
            if modified_count > 0:
                logger.info(f"Tarea {task_id} actualizada a estado: {status}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error al actualizar tarea {task_id}: {e}")
            return False
    
    def update_task_paths(self, task_id: str, minio_path: str = None, parquet_path: str = None) -> bool:
        """Actualizar las rutas de archivos de una tarea"""
        try:
            update_data = {"updated_at": datetime.now()}
            
            if minio_path:
                update_data["minio_path"] = minio_path
            if parquet_path:
                update_data["parquet_path"] = parquet_path
            
            modified_count = self.mongo_manager.update_one(
                self.tasks_collection,
                {"id": task_id},
                update_data
            )
            
            return modified_count > 0
        except Exception as e:
            logger.error(f"Error al actualizar rutas de tarea {task_id}: {e}")
            return False
    
    def close(self):
        """Cerrar conexión a MongoDB"""
        self.mongo_manager.close() 