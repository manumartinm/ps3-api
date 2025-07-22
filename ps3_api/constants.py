import os
from dotenv import load_dotenv
from config import dotenv_path

load_dotenv(dotenv_path)

API_KEY = os.getenv("API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
PS3_BACKEND_CORS_ORIGIN = os.getenv("PS3_BACKEND_CORS_ORIGIN", "*")
