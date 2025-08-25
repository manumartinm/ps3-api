from pydantic import BaseModel, Field
from ps3_shared.entities.task import Task
from typing import Optional


class PDFUploadResponse(BaseModel):
    """Respuesta para la subida de un PDF"""
    success: bool = Field(..., description="Indica si la subida fue exitosa")
    message: str = Field(..., description="Mensaje descriptivo de la operación")
    task: Optional[Task] = Field(None, description="Tarea creada para el procesamiento del PDF")
    error: Optional[str] = Field(None, description="Detalle del error si la operación falló") 