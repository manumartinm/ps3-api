from typing import Any, Optional
from pydantic import BaseModel, Field


class PDFDataResponse(BaseModel):
    """Respuesta para obtener datos de un PDF procesado"""
    success: bool = Field(..., description="Indica si la operación fue exitosa")
    message: str = Field(..., description="Mensaje descriptivo de la operación")
    data: Optional[Any] = Field(None, description="Datos extraídos del PDF en formato JSON")
    error: Optional[str] = Field(None, description="Detalle del error si la operación falló")
    task_id: Optional[str] = Field(None, description="ID de la tarea asociada") 