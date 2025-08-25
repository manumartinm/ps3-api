from typing import List
from pydantic import BaseModel, Field


class FileCategoryInfo(BaseModel):
    """Información sobre una categoría de archivos"""
    count: int = Field(..., description="Número de archivos en esta categoría")
    files: List[str] = Field(default_factory=list, description="Lista de nombres de archivos")


class TaskStructureInfo(BaseModel):
    """Información sobre la estructura de archivos de una tarea"""
    task_id: str = Field(..., description="ID de la tarea")
    structure: dict[str, FileCategoryInfo] = Field(..., description="Estructura de archivos por categoría")
    total_files: int = Field(..., description="Total de archivos en la tarea")


class TaskStructureResponse(BaseModel):
    """Respuesta para obtener información de estructura de archivos"""
    success: bool = Field(..., description="Indica si la operación fue exitosa")
    message: str = Field(..., description="Mensaje descriptivo de la operación")
    data: TaskStructureInfo = Field(..., description="Información de estructura de archivos")
    error: str = Field(None, description="Detalle del error si la operación falló") 