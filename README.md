# PS3 API

API para el procesamiento de PDFs con integración de MinIO, MongoDB y AMQP.

## Endpoints Implementados

### 1. Subida de PDF
- **POST** `/upload-pdf`
- Sube un archivo PDF, lo guarda en MinIO y publica un mensaje en la cola AMQP
- Crea una nueva tarea en MongoDB con estado "pending"
- Requiere autenticación con Bearer token

### 2. Listado de Tareas
- **GET** `/tasks`
- Devuelve todas las tareas activas almacenadas en MongoDB
- Requiere autenticación con Bearer token

### 3. Obtener Tarea Específica
- **GET** `/tasks/{task_id}`
- Devuelve una tarea específica por su ID
- Requiere autenticación con Bearer token

### 4. Obtener Datos de Tarea
- **GET** `/tasks/{task_id}/data?data_type={odds_path|explanations}`
- Devuelve los datos extraídos del PDF en formato JSON
- Lee el archivo parquet específico almacenado en MinIO
- `data_type`: "odds_path" para datos del odds path calculator, "explanations" para explicaciones
- Solo funciona para tareas con estado "completed"
- Requiere autenticación con Bearer token

### 5. Obtener Todos los Datos de Tarea
- **GET** `/tasks/{task_id}/data/all`
- Devuelve ambos tipos de datos (odds_path y explanations) en una sola respuesta
- Solo funciona para tareas con estado "completed"
- Requiere autenticación con Bearer token

### 6. Descargar Archivo Parquet
- **GET** `/tasks/{task_id}/parquet?data_type={odds_path|explanations}`
- Permite descargar el archivo parquet específico de una tarea completada
- `data_type`: "odds_path" para datos del odds path calculator, "explanations" para explicaciones
- Solo funciona para tareas con estado "completed"
- Requiere autenticación con Bearer token

### 7. Obtener Estructura de Archivos
- **GET** `/tasks/{task_id}/structure`
- Devuelve información sobre la estructura de archivos de una tarea
- Incluye conteo y lista de archivos por categoría (PDFs, parquets, otros)
- Requiere autenticación con Bearer token

### 8. Streaming de Eventos en Tiempo Real (SSE)
- **GET** `/tasks/{task_id}/events`
- Endpoint SSE para recibir eventos en tiempo real del procesamiento de una tarea
- Requiere autenticación con Bearer token
- Retorna stream de eventos con progreso, estado y resultados

### 9. Historial de Eventos
- **GET** `/tasks/{task_id}/events/history`
- Devuelve el historial completo de eventos de una tarea
- Requiere autenticación con Bearer token

### 10. Health Check
- **GET** `/health`
- Endpoint de verificación de estado de la API

## Configuración

### Variables de Entorno

Copia el archivo `env.example` a `.env` y configura las siguientes variables:

```bash
# Configuración de la API
API_KEY=your_api_key_here

# Configuración de MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=ps3_webapp
MONGO_COLLECTION_TASKS=tasks

# Configuración de MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET_PDFS=pdfs
MINIO_BUCKET_PARQUETS=parquets

# Configuración de AMQP (RabbitMQ)
AMQP_HOST=localhost
AMQP_PORT=5672
AMQP_USERNAME=guest
AMQP_PASSWORD=guest
AMQP_VIRTUAL_HOST=/
AMQP_QUEUE_PDF_PROCESSING=pdf_processing

# Configuración de CORS
PS3_BACKEND_CORS_ORIGIN=*
```

## Instalación

1. Instalar dependencias:
```bash
uv sync
```

2. Configurar variables de entorno (ver sección anterior)

3. Ejecutar la API:
```bash
python main.py
```

## Flujo de Trabajo

1. **Subida de PDF**: El usuario sube un PDF a través del endpoint `/upload-pdf`
2. **Almacenamiento**: El PDF se guarda en MinIO en el bucket "pdfs"
3. **Creación de Tarea**: Se crea una entrada en MongoDB con estado "pending"
4. **Notificación**: Se publica un mensaje en la cola AMQP "pdf_processing"
5. **Procesamiento**: El worker (ps3-worker) consume el mensaje y procesa el PDF
6. **Resultados**: Los datos extraídos se guardan como dos archivos parquet en MinIO:
   - `odds_path_{filename}.parquet`: Datos del odds path calculator
   - `explanations_{filename}.parquet`: Explicaciones de campos extraídos
7. **Actualización**: El estado de la tarea se actualiza a "completed"
8. **Consulta**: Los usuarios pueden consultar los datos a través de:
   - `/tasks/{task_id}/data?data_type=odds_path` - Solo datos del odds path
   - `/tasks/{task_id}/data?data_type=explanations` - Solo explicaciones
   - `/tasks/{task_id}/data/all` - Ambos tipos de datos

## Estructura de MinIO

### Organización de Archivos por Tarea

Cada tarea tiene su propia carpeta en MinIO con la siguiente estructura:

```
{task_id}/
├── pdfs/
│   └── {filename}.pdf          # Archivo PDF original subido
├── parquets/
│   ├── odds_path_{filename}.parquet      # Datos del odds path calculator
│   └── explanations_{filename}.parquet   # Explicaciones de campos extraídos
└── others/                      # Otros archivos relacionados (si los hay)
    └── {filename}.txt          # Archivos de texto, logs, etc.
```

### Buckets Utilizados

- **`pdfs`**: Almacena los archivos PDF originales y otros archivos relacionados
- **`parquets`**: Almacena los archivos parquet con los datos extraídos

## Estructura de Datos

### Task
- `id`: ID único de la tarea
- `filename`: Nombre del archivo PDF original
- `status`: Estado de la tarea (pending, processing, completed, failed)
- `created_at`: Fecha de creación
- `updated_at`: Fecha de última actualización
- `minio_path`: Ruta del archivo PDF en MinIO
- `parquet_path`: Ruta del archivo parquet en MinIO
- `error_message`: Mensaje de error si la tarea falló
- `processing_started_at`: Cuándo comenzó el procesamiento
- `completed_at`: Cuándo se completó la tarea

## Autenticación

Todos los endpoints (excepto `/health`) requieren autenticación mediante Bearer token en el header:

```
Authorization: Bearer your_api_key_here
```

## Server-Sent Events (SSE)

La API soporta Server-Sent Events para streaming en tiempo real del progreso de las tareas. Los clientes pueden conectarse al endpoint `/tasks/{task_id}/events` para recibir actualizaciones en tiempo real.

### Tipos de Eventos

- **`progress`**: Eventos de progreso con porcentaje y mensaje
- **`status`**: Cambios de estado de la tarea
- **`error`**: Errores durante el procesamiento
- **`completion`**: Tarea completada con resultados

### Ejemplo de Uso

```javascript
const eventSource = new EventSource('/tasks/abc123/events?token=your_token');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Evento recibido:', data);
};

eventSource.addEventListener('progress', function(event) {
    const data = JSON.parse(event.data);
    console.log('Progreso:', data.progress + '% - ' + data.message);
});

eventSource.addEventListener('completion', function(event) {
    const data = JSON.parse(event.data);
    console.log('Tarea completada:', data.results);
    eventSource.close();
});
```

## Rate Limiting

- **Subida de PDFs**: 50 requests por hora
- **Consulta de datos**: 100 requests por hora
- **Descarga de archivos**: 50 requests por hora
- **Estructura de archivos**: 100 requests por hora
- **Streaming SSE**: Sin límite (conexiones persistentes)

## Dependencias

- FastAPI
- Uvicorn
- PyMongo (MongoDB)
- MinIO Python Client
- Pika (AMQP/RabbitMQ)
- Pandas
- PyArrow (para archivos parquet)
- Python-multipart (para subida de archivos)
