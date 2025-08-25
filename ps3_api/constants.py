import os
from dotenv import load_dotenv
from config import dotenv_path

load_dotenv(dotenv_path)

# Configuración de MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ps3_webapp")
MONGO_COLLECTION_TASKS = os.getenv("MONGO_COLLECTION_TASKS", "tasks")

# Configuración de MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET_PDFS = os.getenv("MINIO_BUCKET_PDFS", "pdfs")
MINIO_BUCKET_PARQUETS = os.getenv("MINIO_BUCKET_PARQUETS", "parquets")

# Configuración de AMQP
AMQP_HOST = os.getenv("AMQP_HOST", "localhost")
AMQP_PORT = int(os.getenv("AMQP_PORT", "5672"))
AMQP_USERNAME = os.getenv("AMQP_USERNAME", "guest")
AMQP_PASSWORD = os.getenv("AMQP_PASSWORD", "guest")
AMQP_VIRTUAL_HOST = os.getenv("AMQP_VIRTUAL_HOST", "/")
AMQP_QUEUE_PDF_PROCESSING = os.getenv("AMQP_QUEUE_PDF_PROCESSING", "pdf_processing")

# Configuración de la API
API_KEY = os.getenv("API_KEY", "")
PS3_BACKEND_CORS_ORIGIN = os.getenv("PS3_BACKEND_CORS_ORIGIN", "*") 